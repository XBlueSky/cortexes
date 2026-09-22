#!/usr/bin/env python3
"""Filter a Claude Code transcript JSONL into a discussion-preserving Markdown.

Pipeline (in order of precedence):
  1. Regex layer (safe/deterministic):
     - Skill bootstrap → [skill-load: plugin:name]
     - ANSI strip on user text (CI log residue)
     - Meta-tag removal (<local-command-*>, <system-reminder>, etc.)
     - tool_result paired with its tool_use

  2. rtk filter layer (declarative per-command):
     - Bash tool_result → apply matching rtk filter if any
     - Filter definitions in filters/*.toml (derived from rtk-ai/rtk, MIT)

  3. LLM classifier layer (fail-open safety net):
     - For any block >CLASSIFIER_THRESHOLD bytes that survived 1+2,
       ask sonnet "log" or "content". log → head+tail sample.
     - Cap on number of calls per session. On any failure → keep verbatim.

First principle: preserve context. Compression is best-effort, never at the
cost of silently losing user discussion or tool signal.

That first principle is enforced structurally, not by hoping every filter is
correct. Every step between the transcript bytes and stdout is optional:

  * an unreadable byte decodes to U+FFFD instead of aborting the read
  * a read that tears keeps the records it already had (read_errors=)
  * an unparseable line is skipped              (line_errors=)
  * a filter that raises degrades ONE tool result to verbatim (filter_errors=)
  * a record that cannot be rendered degrades to a breadcrumb  (record_errors=)
  * a whole-body transform that raises leaves the body as it was (body_errors=)
  * a lone surrogate becomes U+FFFD rather than an unencodable stdout
                                                              (surrogates=)
  * and the terminal write itself falls back to a lossy encode before it is
    allowed to produce zero bytes

Each of those is counted in the audit comment, because a silent degradation is
only marginally better than a silent loss. This structure exists because a
code-search MCP payload changed shape, one filter started raising
AttributeError, and — with no guard here — 21 whole session records were
reduced to the string "(filter failed)" by the SessionEnd hook.

The reason every guard has to be here rather than "one big try in main()" is
that main() renders into memory and writes ONCE, at the end: any failure after
the first record costs the entire conversation, not the tail of it. Streaming
the body out as it is rendered would remove that property, but it cannot be
done safely — see the note above write_output().

Usage:
    filter-transcript.py [--until <ISO-8601>] <transcript.jsonl>

--until reconstructs a Raw as it stood at a past instant: records whose
`timestamp` is strictly after the bound are skipped. See parse_instant() for
timezone handling and render_transcript() for what it does NOT do (it is a
filter, not a prefix truncation — see the note there).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from log_dedup import dedup_or_passthrough
from rtk_cmd.dispatch import find_cmd_filter, find_mcp_filter
from rtk_filter import (
    Filter,
    apply_filter,
    find_filter,
    load_filters,
)

SKIP_TYPES = {"attachment", "file-history-snapshot", "permission-mode",
              "system", "last-prompt"}

META_TAG_RES = [
    re.compile(r"<local-command-caveat>.*?</local-command-caveat>", re.DOTALL),
    re.compile(r"<local-command-stdout>.*?</local-command-stdout>", re.DOTALL),
    re.compile(r"<local-command-stderr>.*?</local-command-stderr>", re.DOTALL),
    re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL),
    re.compile(r"<command-message>[^<]*</command-message>", re.DOTALL),
    re.compile(r"<command-args>[^<]*</command-args>", re.DOTALL),
]
CMDNAME_RE = re.compile(r"<command-name>(?P<name>[^<]*)</command-name>")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\[\d[0-9;]*[A-Za-z]")

SKILL_BOOTSTRAP_RE = re.compile(r"\s*Base directory for this skill:\s*(?P<path>\S+)\s*\n")

CLASSIFIER_THRESHOLD = 12 * 1024
CLASSIFIER_CAP = 5
CLASSIFIER_TIMEOUT_S = 20
CLASSIFIER_INPUT_CAP = 8 * 1024
SAMPLE_HEAD_LINES = 20
SAMPLE_TAIL_LINES = 20

TOOL_HDR = "> [tool]"
CLAUDE_HDR = "### Claude"
USER_HDR = "### User"

# The record-skip breadcrumb must NOT wear TOOL_HDR. The chunk assembler in
# render_transcript() glues a tool_result onto chunks[-1] when it starts with
# TOOL_HDR, so a breadcrumb carrying that prefix adopts the NEXT tool's output
# and files it under "[record skipped]" — output attributed to a turn that was
# never rendered is worse than output with no attribution at all.
RECORD_SKIP_HDR = "> [record]"

# Shown when a tool_result has no header to attach to: its tool_use record was
# skipped, dropped by --until, or the assistant emitted text after the call.
ORPHAN_TOOL_HDR = f"{TOOL_HDR} **(output, tool call not in this record)**"

USAGE = "usage: filter-transcript.py [--until <ISO-8601>] <transcript.jsonl>"

TOOL_ARG_PREVIEW = {
    "Bash": ("command", 200),
    "Read": ("file_path", 200),
    "Edit": ("file_path", 200),
    "Write": ("file_path", 200),
    "Glob": ("pattern", 120),
    "Grep": ("pattern", 120),
    "Skill": ("skill", 80),
    "Task": ("description", 120),
    "WebFetch": ("url", 200),
}

CLASSIFIER_PROMPT = """Classify the following text block for preservation strategy.

Respond with EXACTLY ONE WORD (no punctuation, no explanation):

- "log": machine-generated output where meaning is concentrated at head and/or tail
  (CI logs, build output, install/progress logs, stack traces, ls output).
  Can be safely compressed to head+tail sample without losing signal.

- "content": every position may carry meaning
  (source code, config files, documentation, user prose, file contents,
  grep results, error messages, structured data).
  Must NOT be sampled — the middle might be the only part that matters.

When uncertain, respond "content"."""


def compress_skill_bootstrap(text: str) -> str | None:
    m = SKILL_BOOTSTRAP_RE.match(text)
    if not m:
        return None
    path = m.group("path")
    parts = path.rstrip("/").split("/")
    skill_name = parts[-1] if parts else path
    plugin = None
    if "plugins" in parts:
        i = parts.index("plugins")
        if i + 2 < len(parts):
            plugin = parts[i + 2]
    ref = f"{plugin}:{skill_name}" if plugin else skill_name
    return f"[skill-load: {ref}]"


def clean_user_text(s: str) -> tuple[str | None, str | None]:
    cmd_match = CMDNAME_RE.search(s)
    cmd_name = cmd_match.group("name").strip().lstrip("/") if cmd_match else None
    s = ANSI_RE.sub("", s)
    for pat in META_TAG_RES:
        s = pat.sub("", s)
    s = CMDNAME_RE.sub("", s).strip()
    if cmd_name:
        head = f"`/{cmd_name}`"
        return (f"{head}\n\n{s}" if s else head, cmd_name)
    return (s if s else None, None)


def sample_block(text: str, reason: str) -> str:
    lines = text.splitlines()
    if len(lines) <= SAMPLE_HEAD_LINES + SAMPLE_TAIL_LINES + 5:
        return text
    head = "\n".join(lines[:SAMPLE_HEAD_LINES])
    tail = "\n".join(lines[-SAMPLE_TAIL_LINES:])
    omitted = len(lines) - SAMPLE_HEAD_LINES - SAMPLE_TAIL_LINES
    return (
        f"{head}\n"
        f"\n... [{reason}: {omitted} lines omitted, {len(text)} bytes total] ...\n\n"
        f"{tail}"
    )


def compress_log_block(text: str, reason: str, state: dict) -> str:
    """Prefer rtk-style severity-bucketed dedup; fall back to head+tail sample.

    Sampling loses unique errors that live in the middle. Dedup keeps every
    unique signal but collapses repetition — strictly better for severity-
    annotated logs (dmesg, journalctl, CI). For pure prose we fall back to
    sampling, which is what classifier-as-log meant before this path existed.
    """
    deduped, used = dedup_or_passthrough(text)
    if used:
        state["dedup_used"] += 1
        return deduped
    return sample_block(text, reason)


def classify_block(text: str, state: dict) -> str:
    if os.environ.get("CORTEX_NO_CLASSIFIER") == "1":
        state["classifier_skipped"] += 1
        return "content"
    if state["classifier_calls"] >= CLASSIFIER_CAP:
        state["classifier_skipped"] += 1
        return "content"

    state["classifier_calls"] += 1
    env = {**os.environ, "CORTEX_SESSION_RECORDING": "1"}
    truncated = text[:CLASSIFIER_INPUT_CAP]
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "sonnet",
             "--no-session-persistence", CLASSIFIER_PROMPT],
            input=truncated,
            capture_output=True,
            text=True,
            timeout=CLASSIFIER_TIMEOUT_S,
            env=env,
        )
    except Exception:
        # Deliberately broad: the docstring promises "on any failure → keep
        # verbatim", and the narrow (TimeoutExpired, FileNotFoundError, OSError)
        # tuple did not cover it. A lone surrogate anywhere in the block (a
        # half-emoji in tool output survives json.loads happily) makes
        # subprocess.run(text=True, input=...) raise UnicodeEncodeError, which
        # is a ValueError and used to abort the whole render.
        state["classifier_failures"] += 1
        return "content"

    if result.returncode != 0:
        state["classifier_failures"] += 1
        return "content"

    verdict = result.stdout.strip().lower().rstrip(".")
    if verdict in ("log", "content"):
        return verdict
    state["classifier_failures"] += 1
    return "content"


def fmt_tool_use_header(block: dict) -> str:
    name = block.get("name", "?")
    inp = block.get("input", {}) or {}
    key, limit = TOOL_ARG_PREVIEW.get(name, (None, 0))
    if key and key in inp:
        val = str(inp[key]).replace("\n", " ")
        if len(val) > limit:
            val = val[:limit] + "..."
        return f"{TOOL_HDR} **{name}**: `{val}`"
    keys = ", ".join(inp.keys())
    return f"{TOOL_HDR} **{name}**({keys})"


def extract_bash_command(inp: dict) -> str:
    return (inp.get("command") or "").strip()


def tool_result_to_text(tr: dict) -> str:
    content = tr.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n".join(parts)
    return ""


def guarded(state: dict, fn, *args):
    """Run one compression step; on ANY exception count it and return None.

    A filter's job is to make a tool result smaller — never to decide whether
    the session gets recorded at all. Returning None lets the caller fall back
    to the next-most-faithful rendering, so a filter that no longer understands
    its payload costs one uncompressed tool block instead of the whole Raw.

    A filter that returns a non-str is counted the same way: it would crash
    the caller (fmt_tool_output) instead of this frame, which is exactly the
    displacement that made the original bug so expensive.

    state is read/written with .get() so the counter bump can never itself
    raise KeyError from inside the except clause.
    """
    try:
        result = fn(*args)
    except Exception:
        state["filter_errors"] = state.get("filter_errors", 0) + 1
        return None
    if not isinstance(result, str):
        state["filter_errors"] = state.get("filter_errors", 0) + 1
        return None
    return result


def size_bounded(raw_output: str, state: dict) -> str:
    """The no-filter path: keep verbatim unless big enough to ask the classifier."""
    if len(raw_output) <= CLASSIFIER_THRESHOLD:
        return raw_output
    verdict = classify_block(raw_output, state)
    if verdict == "log":
        state["classifier_sampled"] += 1
        compressed = guarded(state, compress_log_block,
                             raw_output, "classified as log", state)
        if compressed is None:
            return raw_output
        return compressed
    return raw_output


def process_tool_result(
    tool_use: dict, raw_output: str, filters: list[Filter], state: dict
) -> str:
    """Compress one tool result. Never raises — worst case returns raw_output.

    The per-step `guarded()` calls below are what keep the fallback faithful
    (a failed MCP filter still gets the generic size logic); this outer
    try/except is the actual total-function guarantee.
    """
    try:
        return _process_tool_result(tool_use, raw_output, filters, state)
    except Exception:
        state["filter_errors"] = state.get("filter_errors", 0) + 1
        return raw_output


def _process_tool_result(
    tool_use: dict, raw_output: str, filters: list[Filter], state: dict
) -> str:
    name = tool_use.get("name")
    inp = tool_use.get("input", {}) or {}

    if not raw_output.strip():
        return ""

    if name == "Task":
        return raw_output

    if isinstance(name, str) and name.startswith("mcp__"):
        mcp_fn = find_mcp_filter(name)
        if mcp_fn is not None:
            filtered = guarded(state, mcp_fn, raw_output, name)
            if filtered is not None:
                if filtered != raw_output:
                    state["mcp_hits"] += 1
                return filtered
            # filter raised: treat this result as if no filter were registered
        # fall through to generic size/classifier logic below

    if name == "Bash":
        cmd = extract_bash_command(inp)
        cmd_fn = find_cmd_filter(cmd) if cmd else None
        if cmd_fn is not None:
            filtered = guarded(state, cmd_fn, raw_output, cmd)
            if filtered is not None:
                state["rtk_cmd_hits"] += 1
                return filtered
            # fall through to the declarative rtk filter, then to size logic
        flt = find_filter(cmd, filters) if cmd else None
        if flt is not None:
            filtered = guarded(state, apply_filter, flt, raw_output)
            if filtered is not None:
                state["rtk_hits"] += 1
                return filtered
        return size_bounded(raw_output, state)

    return size_bounded(raw_output, state)


def fmt_tool_output(text: str) -> str:
    if not text.strip():
        return ""
    return f"\n```output\n{text}\n```"


def process_user_text(raw: str, state: dict) -> str | None:
    skill_ref = compress_skill_bootstrap(raw)
    if skill_ref:
        state["skill_loads"] += 1
        return skill_ref

    cleaned, _ = clean_user_text(raw)
    if cleaned is None:
        return None

    if len(cleaned) > CLASSIFIER_THRESHOLD:
        verdict = classify_block(cleaned, state)
        if verdict == "log":
            state["classifier_sampled"] += 1
            compressed = guarded(state, compress_log_block,
                                 cleaned, "classified as log", state)
            if compressed is not None:
                return compressed
    return cleaned


NAIVE_UNTIL_WARNING = (
    "warning: --until {value!r} carries no timezone and is being read as UTC. "
    "Raw frontmatter stores LOCAL time (a 08:37:45Z record is filed as "
    "`time: 16:37:45` in +08:00), so a bound copied from a Raw needs its "
    "offset — write {text!r} with the local offset appended, e.g. "
    "{text}+08:00, or the bound lands hours away from the record you meant."
)


def parse_instant(value: str, *, warn_naive: bool = False) -> datetime:
    """Parse an ISO-8601 instant into an aware UTC datetime.

    Accepts a trailing "Z" as well as a numeric offset ("+08:00"). A value
    carrying NO timezone is read as UTC, because that is what transcript
    `timestamp` fields are — a naive --until would otherwise silently mean
    something different on a machine in another zone.

    UTC is the right default and also a trap, because the number an operator
    copies is nearly always the LOCAL one in a Raw's frontmatter. Keeping the
    default and shouting about it on stderr is the only combination that is
    both correct for machines and honest to humans, so callers parsing an
    operator-supplied value pass warn_naive=True. record_instant() does not:
    transcript timestamps are always Z-suffixed, and a warning per record
    would bury the one that matters.

    Raises ValueError on anything unparseable; callers must not swallow it
    into "no bound at all".
    """
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"not an ISO-8601 instant: {value!r}") from exc
    if dt.tzinfo is None:
        if warn_naive:
            print("filter-transcript.py: "
                  + NAIVE_UNTIL_WARNING.format(value=value, text=text),
                  file=sys.stderr)
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def record_instant(rec: dict) -> datetime | None:
    """The record's `timestamp` as aware UTC, or None if absent/unparseable.

    None means "no opinion": the caller keeps the record. Dropping content
    because a timestamp was malformed would be the same silent data loss this
    module exists to avoid.
    """
    ts = rec.get("timestamp")
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return parse_instant(ts)
    except ValueError:
        return None


def _render_record(
    rec: dict, tool_uses: dict, chunks: list, filters: list[Filter], state: dict
) -> None:
    t = rec.get("type")

    if t == "assistant":
        # `.get("message", {})` defends against a MISSING key only; a record
        # carrying `"message": null` is common enough to matter.
        content = (rec.get("message") or {}).get("content") or []
        for block in content:
            btype = block.get("type")
            if btype == "text":
                txt = (block.get("text") or "").strip()
                if txt:
                    chunks.append(f"{CLAUDE_HDR}\n\n{txt}\n")
            elif btype == "tool_use":
                tid = block.get("id")
                if tid:
                    tool_uses[tid] = block
                chunks.append(fmt_tool_use_header(block))

    elif t == "user":
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, str):
            state["raw_bytes"] += len(content)
            body = process_user_text(content, state)
            if body:
                state["output_bytes"] += len(body)
                chunks.append(f"{USER_HDR}\n\n{body}\n")
        elif isinstance(content, list):
            for block in content:
                btype = block.get("type")
                if btype == "text":
                    raw = block.get("text") or ""
                    state["raw_bytes"] += len(raw)
                    body = process_user_text(raw, state)
                    if body:
                        state["output_bytes"] += len(body)
                        chunks.append(f"{USER_HDR}\n\n{body}\n")
                elif btype == "tool_result":
                    tid = block.get("tool_use_id")
                    tu = tool_uses.get(tid, {})
                    raw_output = tool_result_to_text(block)
                    state["raw_bytes"] += len(raw_output)
                    processed = process_tool_result(
                        tu, raw_output, filters, state
                    )
                    state["output_bytes"] += len(processed)
                    suffix = fmt_tool_output(processed)
                    if suffix:
                        if chunks and chunks[-1].startswith(TOOL_HDR):
                            chunks[-1] = chunks[-1] + suffix
                        else:
                            # Nothing to attach to. Dropping the block here is
                            # exactly the silent loss this module exists to
                            # prevent, so it gets a header of its own.
                            state["orphan_outputs"] += 1
                            chunks.append(ORPHAN_TOOL_HDR + suffix)


def render_transcript(
    path: Path, filters: list[Filter], until: datetime | None = None
) -> tuple[str, dict]:
    """Render a transcript to Markdown, plus the audit counters.

    `until` drops every record whose `timestamp` is strictly after that
    instant; records with no (or an unparseable) timestamp are always kept.
    Note this is a FILTER, not a prefix truncation: a jsonl is not strictly
    timestamp-ordered, so a caller that needs "the file as it was on disk at
    time T" must truncate the lines itself and pass the prefix.
    """
    state = {
        "skill_loads": 0,
        "rtk_hits": 0,
        "rtk_cmd_hits": 0,
        "mcp_hits": 0,
        "classifier_calls": 0,
        "classifier_sampled": 0,
        "classifier_failures": 0,
        "classifier_skipped": 0,
        "dedup_used": 0,
        "filter_errors": 0,
        "record_errors": 0,
        "line_errors": 0,
        "read_errors": 0,
        "orphan_outputs": 0,
        "raw_bytes": 0,
        "output_bytes": 0,
    }
    tool_uses: dict[str, dict] = {}
    chunks: list[str] = []

    try:
        _read_records(path, tool_uses, chunks, filters, state, until)
    except Exception as exc:
        # The read itself broke (an I/O error, the file going away mid-stream).
        # This is the last place where "accumulate everything, write once" can
        # still cost the whole session: `chunks` already holds a faithful
        # PREFIX of the conversation, so it is emitted with a tombstone
        # instead of discarded.
        #
        # ...unless there is no prefix. A read that produced nothing keeps
        # failing loudly, on purpose: zero bytes of stdout is what makes the
        # SessionEnd hook write the "(filter failed)" stub, and that stub is
        # the marker scripts/backfill-failed-raws.py looks for. Trading it for
        # a two-line Raw would make the failure unfindable later.
        if not chunks:
            raise
        state["read_errors"] = 1
        chunks.append(
            f"{RECORD_SKIP_HDR} **[transcript read aborted: "
            f"{type(exc).__name__}]**"
        )

    out: list[str] = []
    tool_buf: list[str] = []
    for c in chunks:
        if c.startswith(TOOL_HDR):
            tool_buf.append(c)
        else:
            if tool_buf:
                out.append("\n\n".join(tool_buf) + "\n")
                tool_buf = []
            out.append(c)
    if tool_buf:
        out.append("\n\n".join(tool_buf) + "\n")

    return "\n".join(out), state


def _read_records(
    path: Path,
    tool_uses: dict,
    chunks: list,
    filters: list[Filter],
    state: dict,
    until: datetime | None,
) -> None:
    """Stream the transcript into `chunks`. Appends as it goes, so a caller
    that catches a failure here still holds every record read before it."""
    # errors="replace" because this hook is detached with nohup and renders a
    # transcript Claude Code may still be appending to: a read that lands in
    # the middle of a multibyte character is an ordinary race, not corruption.
    # Strict decoding turns that race into UnicodeDecodeError, which escapes
    # every per-record guard below and — since main() writes once, at the end —
    # discarded every record already in `chunks`. One mojibake character costs
    # one character; a strict read cost the session.
    # encoding is pinned rather than inherited: the hook can run under a C/POSIX
    # locale, where the default would be ASCII and every CJK turn would break.
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                # Deliberately broader than JSONDecodeError, for the same
                # reason guarded() is: json.loads raises RecursionError on
                # deeply nested input and MemoryError on a huge one, neither of
                # which is a JSONDecodeError, and either one used to take the
                # whole render down along with every record already rendered.
                state["line_errors"] += 1
                continue
            if not isinstance(rec, dict):
                state["line_errors"] += 1
                continue

            if until is not None:
                ts = record_instant(rec)
                if ts is not None and ts > until:
                    continue

            if rec.get("type") in SKIP_TYPES:
                continue

            # One record with an unexpected internal shape must not cost the
            # whole conversation. Same spirit as the unparseable-line skip
            # above, but visible: the breadcrumb says a turn was lost and why.
            try:
                _render_record(rec, tool_uses, chunks, filters, state)
            except Exception as exc:
                state["record_errors"] = state.get("record_errors", 0) + 1
                chunks.append(
                    f"{RECORD_SKIP_HDR} **[record skipped: "
                    f"{type(exc).__name__}]**"
                )


# Every line boundary Python's str.splitlines() recognises other than "\n".
# Tool results are full of terminal progress output ("...45%\r...50%\r"), and a
# bare "\r" makes every text-mode reader (distill marker writer, git hosting
# pre-receive hooks that parse the diff) count lines differently from git.
_LINE_BREAKS = re.compile(r"\r\n?|[\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]")


def normalize_line_breaks(text: str) -> str:
    """Rewrite every non-"\n" line boundary as "\n".

    Applied once, at capture time, so the bytes that land in Raw/ are the
    bytes every later reader will agree on. Progress-bar redraws become one
    line per redraw, which is also the more readable rendering.
    """
    return _LINE_BREAKS.sub("\n", text)


# Credential shapes that must never reach Raw/. Each pair is (pattern,
# replacement); replacements are chosen so the result matches neither this
# rule again nor the equivalent rule in git hosting secret-check hooks (a
# password-in-URL placeholder therefore starts with "$", the one character
# those hooks exclude). The last, generic rule catches KEY=VALUE environment
# dumps: a key ending in token/key/secret/password/credential followed by a
# 16+ character value that mixes letters and digits.
_SECRET_RULES = [
    (re.compile(r"glpat-[0-9a-zA-Z_\-]{20}"), "glpat-REDACTED"),
    (re.compile(r"gloas-[0-9a-zA-Z_\-]{64}"), "gloas-REDACTED"),
    (re.compile(r"(?i)(A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}"), r"\1-REDACTED"),
    (re.compile(r"sk-(?:proj|svcacct|admin)-[A-Za-z0-9_\-]{20,}"), "sk-REDACTED"),
    (re.compile(r"sk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}"), "sk-REDACTED"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "sk-ant-REDACTED"),
    (re.compile(r"_gitlab_session=[0-9a-z]{32}"), "_gitlab_session=REDACTED"),
    (re.compile(r"\bey[a-zA-Z0-9]{17,}\.ey[a-zA-Z0-9/\\_\-]{17,}\.[a-zA-Z0-9/\\_\-]{10,}={0,2}"),
     "eyJ.REDACTED.JWT"),
    (re.compile(r"(\bcurl\b[^\n]*?(?:-u|--user)(?:=|[ \t]{1,5})[\"']?[^\s\"':@]+:)[^\s\"']{3,}"),
     r"\1REDACTED"),
    # header rules run after the token-shape rules; a value already turned into
    # "<type>-REDACTED" keeps its type marker instead of being flattened
    (re.compile(r"((?i:authorization)[\"']?\s*[:=]\s*[\"']?(?:Bearer|Basic|Token|token|Negotiate)\s+)"
                r"(?![A-Za-z0-9._~+/=\-]*REDACTED)[A-Za-z0-9._~+/=\-]{8,}"), r"\1REDACTED"),
    (re.compile(r"((?i:private-token)[\"']?\s*[:=]\s*[\"']?)(?![A-Za-z0-9_\-]*REDACTED)[A-Za-z0-9_\-]{8,}"),
     r"\1REDACTED"),
    (re.compile(r"([a-zA-Z]{3,10}://[^$\s][^:@/\s]{3,20}:)[^$\s][^:@\s/]{3,40}@"), r"\1${REDACTED}@"),
    # Two quantifiers in this rule used to make it O(n^2) in the length of one
    # contiguous [A-Za-z0-9_.-] run. Measured on the original: 4 KB 1.2s,
    # 8 KB 4.7s, 16 KB 19.1s — ~4x per doubling, crossing the recorder's 600s
    # timeout near 90 KB, at which point the session is not slow, it is gone.
    # The runs that get that long are base64url (its "-" and "_" stay inside
    # the key class where classic base64's "+/=" would break the run), JWT
    # payloads, hex digests and minified identifier soup. Python's re has no
    # atomic groups or possessive quantifiers, so both are fixed structurally:
    #
    #  1. `(?<![A-Za-z0-9_.\-])` pins the match to the START of a key-character
    #     run. Without it the engine retries `[A-Za-z0-9_.\-]*<keyword>` at
    #     every one of n offsets, each costing a full forward scan plus a
    #     char-by-char backtrack. This costs nothing in meaning: the leading
    #     `*` can absorb any prefix, so a match at offset k always implies one
    #     at the run start with the same replacement (the prefix is group 1,
    #     which is copied through verbatim).
    #  2. the two "value mixes letters and digits" lookaheads get an explicit
    #     {0,256} bound. Unbounded they scan to the end of the value run on
    #     every candidate, so text like "key=" repeated before a long run is
    #     quadratic again (measured 23s at 8000 repeats). The bound means a
    #     credential must show its first letter and its first digit within 256
    #     characters; base64, hex, UUID and JWT all do so within a handful.
    #
    # Verified semantics-preserving by differential fuzz against the original
    # over 300k generated strings (0 mismatches) and by replaying the whole
    # 1.15 MB Raw/2026/07/12 record through both (identical output, 1.20s ->
    # 0.23s). Cost is now linear: a 64 KB key-class run redacts in ~0.01s,
    # down from ~5 minutes extrapolated.
    (re.compile(r"(?i)(?<![A-Za-z0-9_.\-])"
                r"((?:[A-Za-z0-9_.\-]*(?:token|key|secret|password|passwd|pwd|credential)s?)"
                r"[\"']?\s*[:=]\s*[\"']?)"
                r"(?=[A-Za-z0-9_\-+/=.]{0,256}\d)"
                r"(?=[A-Za-z0-9_\-+/=.]{0,256}[A-Za-z])"
                r"[A-Za-z0-9_\-+/=.]{16,}"),
     r"\1REDACTED"),
]


# A lone surrogate reaches this module whenever Claude Code truncates a tool
# result on a JS string boundary: the truncation splits a surrogate PAIR, the
# survivor goes through JSON.stringify as a "\udXXX" escape, and json.loads
# materialises it happily. sys.stdout is a strict UTF-8 stream, so it is the
# *write* that raises — after the entire render has succeeded — and the
# SessionEnd hook turns those zero bytes into the "(filter failed)" stub.
#
# Two ways out, and the choice is not a toss-up:
#
#   errors="surrogatepass" is byte-faithful, but it emits WTF-8: three bytes
#   that no conforming UTF-8 decoder will accept, written into Raw/ where git,
#   cortex-vec's embedder, Obsidian and every read_text() in this repo would
#   each have to grow the same exception. And it preserves nothing worth
#   preserving — the byte is half of a character Claude Code already threw the
#   other half of, so no reader can ever reconstruct it.
#
#   Sanitising is lossy in principle and free in practice, for exactly that
#   reason, and it keeps the vault well-formed for every downstream consumer.
#
# So: sanitise. One U+FFFD per lone surrogate, counted as surrogates= in the
# audit so the loss is visible rather than assumed. The blast radius of a
# half-emoji is now one character.
_SURROGATE_RE = re.compile("[\ud800-\udfff]")
# spelled out rather than pasted: a literal U+FFFD in a source file is
# indistinguishable from mojibake in the source file itself
_REPLACEMENT_CHAR = chr(0xFFFD)


def scrub_surrogates(text: str) -> tuple[str, int]:
    """Replace each lone surrogate with U+FFFD; return (text, count)."""
    return _SURROGATE_RE.subn(_REPLACEMENT_CHAR, text)


def write_output(text: str) -> int:
    """Write the finished record to stdout. Returns a process exit code.

    This is the one place where "it raised" and "it rendered nothing" look the
    same to the caller: session-end-record.sh sees an empty stdout either way
    and writes the "(filter failed)" stub. So an encoding failure here must
    cost characters, never the record — the fallback re-encodes with
    errors="replace" and goes straight at the byte stream.

    Only UnicodeEncodeError is retried. TextIOWrapper encodes before it
    buffers, so that failure means nothing was written and a retry is safe;
    a broken pipe or a full disk may have written part of the text already,
    and retrying would duplicate it.

    Note on why this writes ONCE rather than streaming the body as it renders:
    redact_secrets() is a whole-body pass, and a credential that straddles a
    chunk boundary is only visible to it once the whole body exists. Bytes
    already on stdout cannot be recalled, so streaming would trade "a late
    failure costs the record" for "a late failure leaks a token". Guarding
    every late step instead (see the module docstring) buys the same property
    without that trade.
    """
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
        return 0
    except UnicodeEncodeError:
        pass
    except Exception:
        return 1

    buf = getattr(sys.stdout, "buffer", None)
    if buf is None:
        return 1
    try:
        buf.write(text.encode("utf-8", "replace"))
        buf.flush()
    except Exception:
        return 1
    return 0


def redact_secrets(text: str) -> tuple[str, int]:
    """Replace credential-shaped strings with REDACTED placeholders.

    Returns the redacted text and how many replacements were made. Runs at
    capture time so a token printed by a tool never lands in Raw/, whatever
    git hosting the vault is pushed to.
    """
    total = 0
    for pattern, replacement in _SECRET_RULES:
        text, n = pattern.subn(replacement, text)
        total += n
    return text, total


def parse_args(argv: list[str]) -> tuple[Path, datetime | None]:
    """Parse argv[1:] into (transcript path, --until bound).

    Hand-rolled rather than argparse so the single-argument form the SessionEnd
    hook uses keeps its exact contract (usage on stderr, exit 2). Raises
    ValueError with a human-readable message on any bad input — an --until the
    caller cannot parse must fail loudly, never quietly mean "no bound".
    """
    until: datetime | None = None
    positional: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--until":
            i += 1
            if i >= len(argv):
                raise ValueError("--until requires an ISO-8601 value")
            until = parse_instant(argv[i], warn_naive=True)
        elif arg.startswith("--until="):
            until = parse_instant(arg.split("=", 1)[1], warn_naive=True)
        elif arg.startswith("-") and arg != "-":
            raise ValueError(f"unknown option: {arg}")
        else:
            positional.append(arg)
        i += 1
    if len(positional) != 1:
        raise ValueError("exactly one transcript path is required")
    return Path(positional[0]), until


def main() -> int:
    try:
        path, until = parse_args(sys.argv[1:])
    except ValueError as exc:
        print(f"filter-transcript.py: {exc}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2
    if not path.exists():
        return 1

    filters_dir = Path(__file__).parent / "filters"
    # A malformed filters/*.toml is the one failure here with a GLOBAL blast
    # radius — it would abort before a single record is read, stubbing every
    # session in every repo. load_filters already fails open on a missing
    # tomllib; extend that to a bad file. filters_loaded=0 in the audit is the
    # tell that this happened.
    filters_error = 0
    try:
        filters = load_filters(filters_dir)
    except Exception:
        filters = []
        filters_error = 1

    body, state = render_transcript(path, filters, until)

    # The whole-body transforms. Each one is optional in exactly the sense
    # every per-tool filter is optional: the body handed to it is already a
    # faithful record, so a transform that raises must cost its own effect and
    # nothing more. Unguarded, a raise in any of these three reached main()'s
    # caller and the session became the "(filter failed)" stub — the terminal
    # transforms were the last unguarded stretch of the pipeline.
    body_errors = 0

    try:
        body, surrogates = scrub_surrogates(body)
    except Exception:
        body_errors += 1
        surrogates = 0

    try:
        body = normalize_line_breaks(body)
    except Exception:
        body_errors += 1

    try:
        body, redactions = redact_secrets(body)
    except Exception:
        # Emitting an unredacted body is a real cost, not a free fallback; it
        # is still the lesser one, because the alternative destroys the record
        # AND leaves the secret in the transcript. body_errors>0 with
        # redactions=0 is the signal to scan this Raw by hand.
        body_errors += 1
        redactions = 0

    raw = state["raw_bytes"]
    output = state["output_bytes"]
    saved_pct = ((raw - output) * 100 // raw) if raw else 0
    audit = (
        f"<!-- audit: skill_loads={state['skill_loads']} "
        f"rtk_hits={state['rtk_hits']} "
        f"rtk_cmd_hits={state['rtk_cmd_hits']} "
        f"mcp_hits={state['mcp_hits']} "
        f"classifier_calls={state['classifier_calls']} "
        f"classifier_sampled={state['classifier_sampled']} "
        f"classifier_failures={state['classifier_failures']} "
        f"classifier_skipped={state['classifier_skipped']} "
        f"dedup_used={state['dedup_used']} "
        # filter_errors counts drifted PAYLOADS: one misbehaving tool result.
        # filters_error is the load of filters/*.toml itself, whose blast
        # radius is every session in every repo. Folding the second into the
        # first made a broken config indistinguishable from one odd MCP reply,
        # which is the difference between "ignore it" and "stop the world".
        f"filter_errors={state['filter_errors']} "
        f"filters_error={filters_error} "
        f"record_errors={state['record_errors']} "
        f"line_errors={state['line_errors']} "
        f"read_errors={state['read_errors']} "
        f"body_errors={body_errors} "
        f"orphan_outputs={state['orphan_outputs']} "
        f"surrogates={surrogates} "
        f"redactions={redactions} "
        f"raw_bytes={raw} output_bytes={output} saved_pct={saved_pct} "
        f"filters_loaded={len(filters)} -->\n"
    )
    return write_output(audit + body)


if __name__ == "__main__":
    sys.exit(main())
