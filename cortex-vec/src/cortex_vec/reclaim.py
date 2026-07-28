"""Reclaim superseded Raw snapshots — one conversation recorded more than once.

SessionEnd names each Raw by wall-clock (``HHMMSS_session_<repo>.md``), but it
fires more than once per conversation (``/clear``, exit + ``--resume``) and the
transcript it filters is one continuously growing jsonl. Every firing re-filters
the *whole* transcript, so the earlier files are strict prefixes of the latest
one — pure redundancy that would otherwise each sit in the distill queue as its
own entry, spending the distill budget several times over on the same
conversation and landing duplicate Notes.

Two safety properties make removal sound:

* the candidate set is exactly :func:`distill_queue`'s output, i.e. Raw files
  nothing references yet. An already-distilled Raw carries a position-anchored
  ``<!-- distilled: ... -->`` marker and is pointed at by a Note's ``source:``,
  so it is never touched.
* a candidate must be a **prefix** of the survivor, so it carries no line the
  survivor lacks. If the filter output ever diverges (its LLM residue
  classifier is not deterministic) the match simply fails and nothing is
  removed — the failure mode is "duplicate stays", never "content lost".

Comparison starts at the first conversation turn: the frontmatter holds the
wall-clock stamp that differs between recordings of the same session.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .distill_queue import _TURN_HDRS, distill_queue


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


def _covers(survivor: list[str], candidate: list[str]) -> bool:
    """True iff candidate is a non-empty prefix of survivor."""
    return (
        bool(candidate)
        and len(candidate) <= len(survivor)
        and survivor[: len(candidate)] == candidate
    )


def find_superseded(root, keep=None) -> list[Path]:
    """Undistilled Raw files made redundant by a longer recording (FIFO order).

    With ``keep``, only that file is treated as a survivor — the session-end
    path, one body read per queued file. Without it, the whole queue is
    compared pairwise (backlog cleanup). For two byte-identical bodies the
    later path survives, so exactly one of the pair is reclaimed.
    """
    queue = distill_queue(root)
    if keep is not None:
        survivor = _body(keep)
        if not survivor:
            return []
        keep_resolved = Path(keep).resolve()
        return [
            p for p in queue
            if p.resolve() != keep_resolved and _covers(survivor, _body(p))
        ]

    bodies = {p: _body(p) for p in queue}
    superseded = []
    for cand, cand_body in bodies.items():
        for other, other_body in bodies.items():
            if other == cand or not _covers(other_body, cand_body):
                continue
            if len(cand_body) < len(other_body) or str(cand) < str(other):
                superseded.append(cand)
                break
    return superseded


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
    found = find_superseded(root, keep=getattr(args, "keep", None))
    if getattr(args, "apply", False):
        vault = getattr(args, "vault", None)
        if not vault:
            from .config import get_vault_path

            vault = get_vault_path()
        found = apply_reclaim(found, vault=vault)
    for path in found:
        print(path)
