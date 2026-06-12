"""Position-anchored detection of distilled state for Raw session records.

A real distilled marker is a bare whole-line ``<!-- distilled: ... -->`` written
by one of two writers, in one of two positions:

* the **header** — distill's Phase-1 stamp (and broadcast's Step-9 append) goes
  into the top of the file, BEFORE the first conversation turn; or
* the **end of file** — session-end's ``(skip: meta-session)`` stamp is appended
  as the last non-empty line.

A pipeline meta-session's *conversation body* also quotes the marker string many
times (it printfs markers onto OTHER files and every command + output lands in
the transcript), so a body-substring scan such as ``grep -rL '<!-- distilled:'``
is fooled. We anchor to position instead: a marker counts ONLY if it appears
before the first turn header, or as the last non-empty line. Markers strictly
inside the conversation are quotes and ignored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# A real marker occupies a whole (stripped) line.
_TRAILER_RE = re.compile(r"^<!--\s*distilled:.*-->$")
# A broadcast resolution segment lives inside the same marker, after a `|`.
_RESOLVED_RE = re.compile(r"\|\s*(?:broadcast|merged|no-broadcast):")
# filter-transcript.py turn headers (see hooks/scripts/filter-transcript.py).
_TURN_HDRS = frozenset(("### User", "### Claude"))


@dataclass(frozen=True)
class RawState:
    """Distilled state derived from a Raw file's trailer.

    outcome is one of: ``undistilled``, ``new``, ``pending-merge``,
    ``skip-routine``, ``skip-meta``, ``no-insight``, ``no-extractable-content``
    (legacy), or ``unknown`` (trailer present but unparseable).
    """

    outcome: str
    broadcast_resolved: bool = False


def _real_marker(path) -> str | None:
    """Return the authoritative marker line, or None if undistilled.

    Single pass: the first whole-line marker seen before the first conversation
    turn wins (header convention); otherwise the last non-empty line, if it is a
    marker, wins (end-of-file convention). Markers inside the conversation are
    quotes and ignored.
    """
    header_marker = None
    last_nonempty = None
    in_conversation = False
    try:
        with Path(path).open(encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                last_nonempty = stripped
                if not in_conversation:
                    if stripped in _TURN_HDRS:
                        in_conversation = True
                    elif header_marker is None and _TRAILER_RE.match(stripped):
                        header_marker = stripped
    except OSError:
        return None
    if header_marker is not None:
        return header_marker
    if last_nonempty is not None and _TRAILER_RE.match(last_nonempty):
        return last_nonempty
    return None


def _outcome_from_trailer(line: str) -> str:
    # line shape: <!-- distilled: DATE → OUTCOME [| resolution-seg]... -->
    arrow = line.find("→")
    if arrow == -1:
        return "unknown"
    rest = line[arrow + len("→") :].rstrip()
    if rest.endswith("-->"):
        rest = rest[:-3]
    # OUTCOME is everything before the first resolution segment.
    outcome = rest.split("|", 1)[0].strip()
    low = outcome.lower()
    if low.startswith("(skip: meta"):
        return "skip-meta"
    if low.startswith("(skip: routine"):
        return "skip-routine"
    if low.startswith("(no insight"):
        return "no-insight"
    if low.startswith("(no extractable content"):
        return "no-extractable-content"
    if low.startswith("pending-merge:"):
        return "pending-merge"
    if outcome:  # a target path like Notes/X.md or Projects/Y/Z.md
        return "new"
    return "unknown"


def classify(path) -> RawState:
    """Authoritative distilled state of a single Raw file."""
    line = _real_marker(path)
    if line is None:
        return RawState("undistilled")
    return RawState(_outcome_from_trailer(line), bool(_RESOLVED_RE.search(line)))


def is_distilled(state: RawState) -> bool:
    return state.outcome != "undistilled"


def is_broadcast_eligible(state: RawState) -> bool:
    """Eligible iff Phase-1 outcome is new/pending-merge and not yet broadcast."""
    return state.outcome in ("new", "pending-merge") and not state.broadcast_resolved


def _raw_files(root) -> list[Path]:
    return sorted(Path(root).rglob("*.md"))


def distill_queue(root) -> list[Path]:
    """Raw files still awaiting distillation (FIFO by path)."""
    return [p for p in _raw_files(root) if classify(p).outcome == "undistilled"]


def broadcast_queue(root) -> list[Path]:
    """Distilled Raw files eligible for broadcast (FIFO by path)."""
    return [p for p in _raw_files(root) if is_broadcast_eligible(classify(p))]


# --- CLI dispatch (called from cli.py, before the heavy store import) --------


def dispatch_raw_state(path) -> None:
    state = classify(path)
    suffix = " (broadcast-resolved)" if state.broadcast_resolved else ""
    print(f"{state.outcome}{suffix}")


def dispatch_distill_queue(root) -> None:
    for p in distill_queue(root):
        print(p)


def dispatch_broadcast_queue(root) -> None:
    for p in broadcast_queue(root):
        print(p)
