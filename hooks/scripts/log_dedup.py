"""Log-shaped output deduplication.

Port of rtk-ai/rtk's `src/cmds/system/log_cmd.rs` (MIT, © rtk-ai contributors).

When the classifier judges a block as `log`, head+tail sampling loses unique
errors that live in the middle. This module normalizes each line (strip
timestamps / UUIDs / hex / large numbers / paths to placeholders), buckets by
severity (error / warn / info), deduplicates within buckets, and emits a
summary that preserves every unique signal while collapsing repetition.
"""
from __future__ import annotations

import re
from collections import OrderedDict

TIMESTAMP_RE = re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}[.,]?\d*\s*")
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
HEX_RE = re.compile(r"0x[0-9a-fA-F]+")
NUM_RE = re.compile(r"\b\d{4,}\b")
PATH_RE = re.compile(r"/[\w./\-]+")

ERROR_KEYWORDS = ("error", "fatal", "panic", "critical", "alert", "emerg", "severe")
WARN_KEYWORDS = ("warn", "notice")
INFO_KEYWORDS = ("info",)

MAX_LOG_ERRORS = 10
MAX_LOG_WARNS = 5
LINE_TRUNCATE = 100


def normalize_log_line(line: str) -> str:
    s = TIMESTAMP_RE.sub("", line)
    s = UUID_RE.sub("<UUID>", s)
    s = HEX_RE.sub("<HEX>", s)
    s = NUM_RE.sub("<NUM>", s)
    s = PATH_RE.sub("<PATH>", s)
    return s.strip()


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 3] + "..."


def _classify(line_lower: str) -> str | None:
    if any(kw in line_lower for kw in ERROR_KEYWORDS):
        return "error"
    if any(kw in line_lower for kw in WARN_KEYWORDS):
        return "warn"
    if any(kw in line_lower for kw in INFO_KEYWORDS):
        return "info"
    return None


def analyze_logs(content: str) -> str:
    error_counts: dict[str, int] = OrderedDict()
    warn_counts: dict[str, int] = OrderedDict()
    info_counts: dict[str, int] = OrderedDict()
    error_originals: dict[str, str] = {}
    warn_originals: dict[str, str] = {}

    for line in content.splitlines():
        bucket = _classify(line.lower())
        if bucket is None:
            continue
        normalized = normalize_log_line(line)
        if bucket == "error":
            if normalized not in error_counts:
                error_originals[normalized] = line
            error_counts[normalized] = error_counts.get(normalized, 0) + 1
        elif bucket == "warn":
            if normalized not in warn_counts:
                warn_originals[normalized] = line
            warn_counts[normalized] = warn_counts.get(normalized, 0) + 1
        else:
            info_counts[normalized] = info_counts.get(normalized, 0) + 1

    total_errors = sum(error_counts.values())
    total_warnings = sum(warn_counts.values())
    total_info = sum(info_counts.values())

    out: list[str] = [
        "Log Summary",
        f"   [error] {total_errors} errors ({len(error_counts)} unique)",
        f"   [warn] {total_warnings} warnings ({len(warn_counts)} unique)",
        f"   [info] {total_info} info messages",
        "",
    ]

    if error_counts:
        out.append("[ERRORS]")
        ordered = sorted(error_counts.items(), key=lambda kv: kv[1], reverse=True)
        for normalized, count in ordered[:MAX_LOG_ERRORS]:
            original = error_originals.get(normalized, normalized)
            truncated = _truncate(original, LINE_TRUNCATE)
            if count > 1:
                out.append(f"   [x{count}] {truncated}")
            else:
                out.append(f"   {truncated}")
        if len(ordered) > MAX_LOG_ERRORS:
            out.append(f"   ... +{len(ordered) - MAX_LOG_ERRORS} more unique errors")
        out.append("")

    if warn_counts:
        out.append("[WARNINGS]")
        ordered = sorted(warn_counts.items(), key=lambda kv: kv[1], reverse=True)
        for normalized, count in ordered[:MAX_LOG_WARNS]:
            original = warn_originals.get(normalized, normalized)
            truncated = _truncate(original, LINE_TRUNCATE)
            if count > 1:
                out.append(f"   [x{count}] {truncated}")
            else:
                out.append(f"   {truncated}")
        if len(ordered) > MAX_LOG_WARNS:
            out.append(f"   ... +{len(ordered) - MAX_LOG_WARNS} more unique warnings")

    return "\n".join(out)


def dedup_or_passthrough(text: str) -> tuple[str, bool]:
    """Return (output, dedup_was_used).

    Apply dedup. If the result is shorter than the input, return it. Otherwise
    fall through — caller decides whether to head+tail sample or keep verbatim.
    """
    result = analyze_logs(text)
    if not result.strip() or len(result) >= len(text):
        return text, False
    return result, True
