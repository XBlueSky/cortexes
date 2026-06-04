#!/usr/bin/env python3
"""Detect cortex maintenance-pipeline sessions.

The SessionEnd hook records every session into Raw/. But sessions whose whole
purpose is maintaining the vault — distilling, compiling the weekly, broadcasting
into related pages, bootstrapping — would otherwise be re-recorded as fresh Raw
and re-enter their own distill queue. The queue could then never reach empty: a
distill run always leaves one trailing self-referential record behind.

We don't drop these sessions (they stay as an audit trail); the caller stamps a
`<!-- distilled: ... (skip: meta) -->` marker so they never re-enter the queue.

Detection is precise-by-design. We match ONLY the pure-maintenance skills via a
structured `Skill` tool_use. We deliberately do NOT match:
  - cortex:evolve / cortex:query — fire inside normal work sessions worth recording
  - cortex:using-cortex          — auto-loaded every session (would flag everything)
  - a mere text mention of "cortex:distill" (e.g. editing the distill code) —
    only an actual Skill invocation counts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Pure vault-maintenance skills. A session that invokes one of these does no
# original work — it only processes the vault.
#
# Each appears in transcripts under TWO ids: the slash-command alias
# (`cortex:distill`) and the dominant plugin:skill id (`cortex:cortex-distill`).
# Both must be matched. Deliberately excluded in both forms: evolve, query,
# using-cortex — those fire inside normal work sessions worth recording.
_PIPELINE = ("distill", "weekly", "broadcast", "genesis")
META_SESSION_SKILLS = frozenset(
    [f"cortex:{name}" for name in _PIPELINE]
    + [f"cortex:cortex-{name}" for name in _PIPELINE]
)


def is_meta_session(path: Path) -> bool:
    """True if the transcript invokes a cortex maintenance-pipeline skill."""
    try:
        with Path(path).open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                content = (rec.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use" or block.get("name") != "Skill":
                        continue
                    skill = (block.get("input") or {}).get("skill", "")
                    if skill in META_SESSION_SKILLS:
                        return True
    except OSError:
        return False
    return False


def main(argv: list[str]) -> int:
    """CLI for the bash hook. Exit 0 = meta, 1 = not meta, 2 = usage error."""
    if len(argv) != 2:
        print("usage: meta_session.py <transcript.jsonl>", file=sys.stderr)
        return 2
    return 0 if is_meta_session(Path(argv[1])) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
