"""Port of rtk-ai/rtk's TOML filter engine.

Derived from https://github.com/rtk-ai/rtk (MIT License, © rtk-ai contributors).
Original Rust implementation: src/core/toml_filter.rs.

We only port the declarative TOML-driven pipeline. rtk's Rust-coded per-command
modules (git diff, npm, cargo, pytest, etc.) are NOT ported — tool_results from
those commands are left to the classifier or kept verbatim.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\[\d[0-9;]*[A-Za-z]")


@dataclass
class ReplaceRule:
    pattern: re.Pattern
    replacement: str


@dataclass
class MatchOutputRule:
    pattern: re.Pattern
    message: str
    unless: re.Pattern | None = None


@dataclass
class Filter:
    name: str
    match_regex: re.Pattern
    strip_ansi: bool = False
    replace: list[ReplaceRule] = field(default_factory=list)
    match_output: list[MatchOutputRule] = field(default_factory=list)
    strip_lines: list[re.Pattern] = field(default_factory=list)
    keep_lines: list[re.Pattern] = field(default_factory=list)
    truncate_lines_at: int | None = None
    head_lines: int | None = None
    tail_lines: int | None = None
    max_lines: int | None = None
    on_empty: str | None = None


def _compile_filter(name: str, definition: dict) -> Filter | None:
    strip_patterns = definition.get("strip_lines_matching", [])
    keep_patterns = definition.get("keep_lines_matching", [])
    if strip_patterns and keep_patterns:
        return None

    try:
        flt = Filter(
            name=name,
            match_regex=re.compile(definition["match_command"]),
            strip_ansi=definition.get("strip_ansi", False),
            replace=[
                ReplaceRule(re.compile(r["pattern"]), r["replacement"])
                for r in definition.get("replace", [])
            ],
            match_output=[
                MatchOutputRule(
                    pattern=re.compile(r["pattern"]),
                    message=r["message"],
                    unless=re.compile(r["unless"]) if r.get("unless") else None,
                )
                for r in definition.get("match_output", [])
            ],
            strip_lines=[re.compile(p) for p in strip_patterns],
            keep_lines=[re.compile(p) for p in keep_patterns],
            truncate_lines_at=definition.get("truncate_lines_at"),
            head_lines=definition.get("head_lines"),
            tail_lines=definition.get("tail_lines"),
            max_lines=definition.get("max_lines"),
            on_empty=definition.get("on_empty"),
        )
        return flt
    except (re.error, KeyError):
        return None


def load_filters(filters_dir: Path) -> list[Filter]:
    filters: list[Filter] = []
    if tomllib is None:
        # No TOML parser (Python < 3.11 without tomli). Fail open: degrade to
        # an empty filter set so the caller keeps tool output verbatim rather
        # than crashing the whole SessionEnd filter pipeline.
        return filters
    for path in sorted(filters_dir.glob("*.toml")):
        try:
            data = tomllib.loads(path.read_text())
        except tomllib.TOMLDecodeError:
            continue
        for name, definition in data.get("filters", {}).items():
            compiled = _compile_filter(name, definition)
            if compiled is not None:
                filters.append(compiled)
    return filters


def find_filter(command: str, filters: list[Filter]) -> Filter | None:
    for f in filters:
        if f.match_regex.search(command):
            return f
    return None


def _truncate_line(line: str, max_chars: int) -> str:
    if len(line) <= max_chars:
        return line
    return line[:max_chars] + "…"


def apply_filter(flt: Filter, stdout: str) -> str:
    lines = stdout.splitlines()

    if flt.strip_ansi:
        lines = [ANSI_RE.sub("", line) for line in lines]

    if flt.replace:
        new_lines = []
        for line in lines:
            for rule in flt.replace:
                line = rule.pattern.sub(rule.replacement, line)
            new_lines.append(line)
        lines = new_lines

    if flt.match_output:
        blob = "\n".join(lines)
        for rule in flt.match_output:
            if rule.pattern.search(blob):
                if rule.unless and rule.unless.search(blob):
                    continue
                return rule.message

    if flt.strip_lines:
        lines = [l for l in lines if not any(p.search(l) for p in flt.strip_lines)]
    elif flt.keep_lines:
        lines = [l for l in lines if any(p.search(l) for p in flt.keep_lines)]

    if flt.truncate_lines_at is not None:
        lines = [_truncate_line(l, flt.truncate_lines_at) for l in lines]

    total = len(lines)
    head, tail = flt.head_lines, flt.tail_lines
    if head is not None and tail is not None:
        if total > head + tail:
            omitted = total - head - tail
            lines = (
                lines[:head]
                + [f"... ({omitted} lines omitted)"]
                + lines[total - tail:]
            )
    elif head is not None:
        if total > head:
            omitted = total - head
            lines = lines[:head] + [f"... ({omitted} lines omitted)"]
    elif tail is not None:
        if total > tail:
            omitted = total - tail
            lines = [f"... ({omitted} lines omitted)"] + lines[omitted:]

    if flt.max_lines is not None and len(lines) > flt.max_lines:
        truncated = len(lines) - flt.max_lines
        lines = lines[:flt.max_lines] + [f"... ({truncated} lines truncated)"]

    result = "\n".join(lines)
    if not result.strip() and flt.on_empty:
        return flt.on_empty
    return result
