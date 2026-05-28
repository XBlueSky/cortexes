"""Filters for list-shaped Bash command outputs: find / grep / ls / tree / wc.

Approach: pragmatic Python ports of rtk-ai/rtk's `src/cmds/system/*.rs`
algorithms (MIT, © rtk-ai contributors), stripped of rtk's command-runner
machinery — cortex receives the stdout after the command already ran.

For these list-shaped commands the win is purely structural: head+tail cap
on plain listings, file-grouped cap on grep-style file:line:content output,
and drop-trailing-summary on tree. Anything that escapes the local heuristic
falls through verbatim — cortex still has the 12 KB classifier safety net
behind it.
"""
from __future__ import annotations

import re
from collections import OrderedDict

# Defaults sized for typical AI-driven Bash invocations (rtk uses similar
# numbers via core::config::limits()).
FIND_HEAD = 30
FIND_TAIL = 10
GREP_PER_FILE = 5
GREP_GLOBAL = 50
GREP_LINE_LEN = 200
LS_MAX_ENTRIES = 80
TREE_MAX_LINES = 200

# `N matches`, `N directories, M files`, etc. — tree(1) / find(1) summary tails.
_TREE_SUMMARY_RE = re.compile(r"^\s*\d+\s+director(y|ies),\s+\d+\s+files?\s*$")
# `total 1234` — first line of `ls -l`
_LS_TOTAL_RE = re.compile(r"^total\s+\d+\s*$")
# `file:line:content` — recursive grep / `grep -n` standard shape
_GREP_LINE_RE = re.compile(r"^([^:]+):(\d+):(.*)$")


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 3] + "..."


def _head_tail_cap(lines: list[str], head: int, tail: int, label: str) -> list[str]:
    if len(lines) <= head + tail + 5:
        return lines
    omitted = len(lines) - head - tail
    return (
        lines[:head]
        + [f"... ({omitted} {label} omitted) ..."]
        + lines[-tail:]
    )


def filter_find(output: str, _command: str = "") -> str:
    """find prints one path per line; head+tail cap is enough."""
    lines = output.splitlines()
    if len(lines) <= FIND_HEAD + FIND_TAIL + 5:
        return output
    return "\n".join(_head_tail_cap(lines, FIND_HEAD, FIND_TAIL, "paths"))


def filter_grep(output: str, _command: str = "") -> str:
    """Group `file:line:content` matches by file, per-file + global cap.

    Mirrors rtk grep_cmd's algorithm. Non-`file:line:content` lines are kept
    verbatim at the top so things like `--count` / `-l` flag outputs survive.
    """
    by_file: "OrderedDict[str, list[tuple[str, str]]]" = OrderedDict()
    other_lines: list[str] = []
    total_matches = 0

    for raw_line in output.splitlines():
        m = _GREP_LINE_RE.match(raw_line)
        if not m:
            if raw_line.strip():
                other_lines.append(raw_line)
            continue
        file_, line_num, content = m.group(1), m.group(2), m.group(3)
        by_file.setdefault(file_, []).append((line_num, content.strip()))
        total_matches += 1

    if not by_file:
        # Nothing matched our standard grep shape — return verbatim.
        return output

    shown = 0
    parts: list[str] = []
    parts.append(f"{total_matches} matches in {len(by_file)} files:")
    parts.append("")
    for file_, matches in by_file.items():
        if shown >= GREP_GLOBAL:
            break
        for line_num, content in matches[:GREP_PER_FILE]:
            if shown >= GREP_GLOBAL:
                break
            parts.append(f"{file_}:{line_num}: {_truncate(content, GREP_LINE_LEN)}")
            shown += 1

    if total_matches > shown:
        parts.append(f"[+{total_matches - shown} more matches omitted]")

    if other_lines:
        parts.append("")
        parts.extend(other_lines)

    result = "\n".join(parts)
    return result if len(result) < len(output) else output


def filter_ls(output: str, _command: str = "") -> str:
    """Drop `total N` header, head+tail cap if listing is huge.

    rtk's full ls compactor reformats every entry into `name size` — too
    fragile across locales. We keep entries verbatim and just cap line count.
    """
    lines = [l for l in output.splitlines() if not _LS_TOTAL_RE.match(l)]
    if len(lines) <= LS_MAX_ENTRIES + 5:
        return "\n".join(lines)
    return "\n".join(_head_tail_cap(lines, LS_MAX_ENTRIES - 10, 10, "entries"))


def filter_tree(output: str, _command: str = "") -> str:
    """Drop trailing `N directories, M files` summary; cap if huge."""
    lines = output.splitlines()
    # Strip the rtk summary tail; tolerate one blank line above it.
    while lines and (
        not lines[-1].strip() or _TREE_SUMMARY_RE.match(lines[-1])
    ):
        lines.pop()

    if len(lines) <= TREE_MAX_LINES + 5:
        return "\n".join(lines)
    return "\n".join(_head_tail_cap(lines, TREE_MAX_LINES - 20, 20, "tree lines"))


def filter_wc(output: str, _command: str = "") -> str:
    """wc -l on large file lists can be many KB. Keep totals line + cap."""
    lines = output.splitlines()
    if len(lines) <= 40:
        return output
    # wc -l output ends with a `... total` line when called with multiple files
    last = lines[-1] if lines and "total" in lines[-1] else None
    body = _head_tail_cap(lines[:-1] if last else lines, 20, 10, "wc entries")
    if last:
        body.append(last)
    return "\n".join(body)


def filter_cat_like(output: str, _command: str = "") -> str:
    """cat/head/tail outputs are user-requested content — leave alone.

    Provided so dispatch can route these commands to an explicit no-op
    rather than triggering the 12 KB classifier. Avoids the classifier
    cost when the user explicitly asked to read a file.
    """
    return output
