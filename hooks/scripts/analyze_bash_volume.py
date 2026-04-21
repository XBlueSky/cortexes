#!/usr/bin/env python3
"""Debug helper: for a transcript, rank Bash commands by output volume.

Used to decide which rtk command modules to port next — commands that produce
the most bytes of tool_result are the ones where porting a dedicated filter
will pay off.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


def first_token(cmd: str) -> str:
    """Collapse `cargo test foo`, `cargo build --release` → `cargo`."""
    parts = cmd.strip().split()
    if not parts:
        return "<empty>"
    head = parts[0]
    # drop path prefix
    head = head.rsplit("/", 1)[-1]
    # for cargo/git, show subcommand too
    if head in ("cargo", "git", "npm", "pnpm", "yarn", "python", "python3"):
        if len(parts) > 1:
            return f"{head} {parts[1]}"
    return head


def analyze(path: Path) -> None:
    tool_uses: dict[str, dict] = {}
    volumes: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)

    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            t = rec.get("type")
            if t == "assistant":
                for blk in rec.get("message", {}).get("content") or []:
                    if blk.get("type") == "tool_use":
                        tid = blk.get("id")
                        if tid:
                            tool_uses[tid] = blk
            elif t == "user":
                content = rec.get("message", {}).get("content")
                if not isinstance(content, list):
                    continue
                for blk in content:
                    if blk.get("type") != "tool_result":
                        continue
                    tu = tool_uses.get(blk.get("tool_use_id"), {})
                    if tu.get("name") != "Bash":
                        continue
                    cmd = (tu.get("input", {}) or {}).get("command", "") or ""
                    head = first_token(cmd)
                    # measure the tool_result text
                    c = blk.get("content")
                    if isinstance(c, str):
                        size = len(c)
                    elif isinstance(c, list):
                        size = sum(
                            len(it.get("text", ""))
                            for it in c
                            if isinstance(it, dict) and it.get("type") == "text"
                        )
                    else:
                        size = 0
                    volumes[head] += size
                    counts[head] += 1

    print(f"=== {path.name} ===")
    print(f"{'command':<30} {'count':>6} {'total_bytes':>14} {'avg_bytes':>12}")
    for head, total in sorted(volumes.items(), key=lambda kv: kv[1], reverse=True)[:20]:
        n = counts[head]
        print(f"{head:<30} {n:>6} {total:>14,} {total // n:>12,}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        analyze(Path(p))
        print()
