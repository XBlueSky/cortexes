#!/usr/bin/env python3
"""Print Bash tool_results larger than N bytes from a transcript.

Helps identify which specific commands produce big uncompressed blocks —
candidates for the next rtk_cmd port.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


THRESHOLD = 12 * 1024


def main(paths: list[str]) -> None:
    for p in paths:
        print(f"=== {Path(p).name} ===")
        tool_uses: dict[str, dict] = {}
        rows: list[tuple[int, str, str]] = []
        with open(p) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") == "assistant":
                    for blk in rec.get("message", {}).get("content") or []:
                        if blk.get("type") == "tool_use":
                            tid = blk.get("id")
                            if tid:
                                tool_uses[tid] = blk
                elif rec.get("type") == "user":
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
                        c = blk.get("content")
                        if isinstance(c, str):
                            size = len(c)
                            text = c
                        elif isinstance(c, list):
                            text = "\n".join(
                                it.get("text", "")
                                for it in c
                                if isinstance(it, dict) and it.get("type") == "text"
                            )
                            size = len(text)
                        else:
                            size = 0
                            text = ""
                        if size >= THRESHOLD:
                            preview = text.splitlines()[0][:80] if text else ""
                            rows.append((size, cmd[:80], preview))

        rows.sort(reverse=True)
        for size, cmd, first in rows:
            print(f"  {size:>8,}  {cmd}")
            print(f"             [first line] {first}")
        print(f"  total large blocks: {len(rows)}")
        print()


if __name__ == "__main__":
    main(sys.argv[1:])
