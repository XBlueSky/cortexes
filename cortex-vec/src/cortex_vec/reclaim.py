"""Reclaim superseded Raw snapshots — one conversation recorded more than once.

SessionEnd names each Raw by wall-clock (``HHMMSS_session_<repo>.md``), but it
fires more than once per conversation (``/clear``, exit + ``--resume``) and the
transcript it filters is one continuously growing jsonl. Every firing re-filters
the *whole* transcript, so the earlier files are strict prefixes of the latest
one — pure redundancy that would otherwise each sit in the distill queue as its
own entry, spending the distill budget several times over on the same
conversation and landing duplicate Notes.

Three safety properties make removal sound:

* the candidate set is exactly :func:`distill_queue`'s output, i.e. Raw files
  nothing references yet. An already-distilled Raw carries a position-anchored
  ``<!-- distilled: ... -->`` marker and is pointed at by a Note's ``source:``,
  so it is never touched.
* a candidate must be a **prefix** of the survivor, so it carries no line the
  survivor lacks. If the filter output ever diverges (its LLM residue
  classifier is not deterministic) the match simply fails and nothing is
  removed — the failure mode is "duplicate stays", never "content lost".
* both files must carry the same ``repo:`` label. A prefix alone does not prove
  redundancy: one conversation whose cwd changes mid-session produces two Raws
  from the same growing transcript but under DIFFERENT repo labels, and the
  earlier one may be that repo's only record, so reclaiming it would erase that
  repo from the vault's history of the period entirely. Such a
  pair is refused and reported (see :class:`CrossRepoPair`) rather than dropped
  in silence — a cross-repo prefix pair is worth an operator's attention.

Comparison starts at the first conversation turn: the frontmatter holds the
wall-clock stamp that differs between recordings of the same session.
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .distill_queue import _TURN_HDRS, distill_queue

# `repo: <name>` inside the leading frontmatter block, as session-end writes it.
_REPO_RE = re.compile(r"^repo:\s*(.*?)\s*$")


def _body(path) -> list[str]:
    """Conversation body: lines from the first turn header to EOF.

    Returns ``[]`` for a file with no turn header (filter failure, truncation).
    An empty body is a prefix of everything, so it must never match.
    """
    lines: list[str] = []
    started = False
    try:
        with Path(path).open(encoding="utf-8") as f:
            for line in f:
                if not started:
                    if line.strip() not in _TURN_HDRS:
                        continue
                    started = True
                lines.append(line.rstrip("\n"))
    except OSError:
        return []
    return lines


def _repo(path) -> str:
    """The ``repo:`` label from the leading frontmatter block.

    Returns ``""`` when the file has no frontmatter or no ``repo:`` key — an
    unlabelled Raw therefore differs from every labelled one and is refused,
    which is the safe direction.
    """
    try:
        with Path(path).open(encoding="utf-8") as f:
            if f.readline().rstrip("\n") != "---":
                return ""
            for line in f:
                stripped = line.rstrip("\n")
                if stripped == "---" or stripped.strip() in _TURN_HDRS:
                    break
                m = _REPO_RE.match(stripped)
                if m:
                    return m.group(1)
    except OSError:
        return ""
    return ""


def _covers(survivor: list[str], candidate: list[str]) -> bool:
    """True iff candidate is a non-empty prefix of survivor."""
    return (
        bool(candidate)
        and len(candidate) <= len(survivor)
        and survivor[: len(candidate)] == candidate
    )


@dataclass(frozen=True)
class CrossRepoPair:
    """A prefix pair reclaim refused because the two Raws name different repos."""

    candidate: Path
    survivor: Path
    candidate_repo: str
    survivor_repo: str

    def describe(self) -> str:
        return (
            f"refused: {self.candidate} (repo: {self.candidate_repo or '?'}) is a "
            f"prefix of {self.survivor} (repo: {self.survivor_repo or '?'}) — "
            "different repo, kept"
        )


@dataclass(frozen=True)
class ReclaimScan:
    """Outcome of one scan: what may go, and what was refused and why."""

    superseded: list[Path] = field(default_factory=list)
    refused: list[CrossRepoPair] = field(default_factory=list)


def scan(root, keep=None) -> ReclaimScan:
    """Undistilled Raw files made redundant by a longer recording (FIFO order).

    With ``keep``, only that file is treated as a survivor — the session-end
    path, one body read per queued file. Without it, the whole queue is
    compared pairwise (backlog cleanup). For two byte-identical bodies the
    later path survives, so exactly one of the pair is reclaimed.

    A prefix pair whose ``repo:`` labels differ lands in ``refused`` instead of
    ``superseded``: the candidate stays on disk and the pair is reported.
    """
    queue = distill_queue(root)
    if keep is not None:
        survivor = _body(keep)
        if not survivor:
            return ReclaimScan()
        keep_path = Path(keep)
        keep_resolved = keep_path.resolve()
        keep_repo = _repo(keep_path)
        result = ReclaimScan()
        for p in queue:
            if p.resolve() == keep_resolved or not _covers(survivor, _body(p)):
                continue
            cand_repo = _repo(p)
            if cand_repo != keep_repo:
                result.refused.append(
                    CrossRepoPair(p, keep_path, cand_repo, keep_repo)
                )
                continue
            result.superseded.append(p)
        return result

    bodies = {p: _body(p) for p in queue}
    repos = {p: _repo(p) for p in queue}
    result = ReclaimScan()
    for cand, cand_body in bodies.items():
        pending: list[CrossRepoPair] = []
        for other, other_body in bodies.items():
            if other == cand or not _covers(other_body, cand_body):
                continue
            if not (len(cand_body) < len(other_body) or str(cand) < str(other)):
                continue
            if repos[cand] != repos[other]:
                pending.append(
                    CrossRepoPair(cand, other, repos[cand], repos[other])
                )
                continue
            # A same-repo survivor settles it; the cross-repo near-misses seen
            # on the way are not worth reporting once the file is going anyway.
            result.superseded.append(cand)
            pending = []
            break
        result.refused.extend(pending)
    return result


def find_superseded(root, keep=None) -> list[Path]:
    """The reclaimable subset of :func:`scan` (refusals dropped)."""
    return scan(root, keep=keep).superseded


def _git_rm(vault, path) -> bool:
    try:
        proc = subprocess.run(
            ["git", "-C", str(vault), "rm", "-q", "-f", "--", str(path)],
            capture_output=True, text=True,
        )
    except OSError:
        return False
    return proc.returncode == 0 and not Path(path).exists()


def apply_reclaim(paths, vault=None) -> list[Path]:
    """Remove the given Raw files; return the ones actually gone.

    Prefers ``git rm`` so the deletion is staged for the vault's auto-commit
    (and therefore recoverable from history); falls back to unlink for files
    git does not track, e.g. when ``git.auto_commit`` is off.
    """
    removed = []
    for path in paths:
        path = Path(path)
        if vault is not None and _git_rm(vault, path):
            removed.append(path)
            continue
        try:
            path.unlink()
        except OSError:
            continue
        removed.append(path)
    return removed


def dispatch(args) -> None:
    root = getattr(args, "root", None)
    if not root:
        from .config import get_vault_path

        root = get_vault_path() / "Raw"
    result = scan(root, keep=getattr(args, "keep", None))
    found = result.superseded
    if getattr(args, "apply", False):
        vault = getattr(args, "vault", None)
        if not vault:
            from .config import get_vault_path

            vault = get_vault_path()
        found = apply_reclaim(found, vault=vault)
    for path in found:
        print(path)
    # Refusals go to stderr in BOTH modes: stdout is the machine-readable list
    # of reclaimed paths (session-end-record.sh counts its lines for the commit
    # message), so a refusal printed there would be miscounted as a removal.
    for pair in result.refused:
        print(pair.describe(), file=sys.stderr)
