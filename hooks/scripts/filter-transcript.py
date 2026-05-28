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
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
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
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
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


def process_tool_result(
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
            filtered = mcp_fn(raw_output, name)
            if filtered != raw_output:
                state["mcp_hits"] += 1
            return filtered
        # fall through to generic size/classifier logic below

    if name == "Bash":
        cmd = extract_bash_command(inp)
        cmd_fn = find_cmd_filter(cmd) if cmd else None
        if cmd_fn is not None:
            state["rtk_cmd_hits"] += 1
            return cmd_fn(raw_output, cmd)
        flt = find_filter(cmd, filters) if cmd else None
        if flt is not None:
            filtered = apply_filter(flt, raw_output)
            state["rtk_hits"] += 1
            return filtered
        if len(raw_output) <= CLASSIFIER_THRESHOLD:
            return raw_output
        verdict = classify_block(raw_output, state)
        if verdict == "log":
            state["classifier_sampled"] += 1
            return compress_log_block(raw_output, "classified as log", state)
        return raw_output

    if len(raw_output) <= CLASSIFIER_THRESHOLD:
        return raw_output
    verdict = classify_block(raw_output, state)
    if verdict == "log":
        state["classifier_sampled"] += 1
        return compress_log_block(raw_output, "classified as log", state)
    return raw_output


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
            return compress_log_block(cleaned, "classified as log", state)
    return cleaned


def render_transcript(path: Path, filters: list[Filter]) -> tuple[str, dict]:
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
        "raw_bytes": 0,
        "output_bytes": 0,
    }
    tool_uses: dict[str, dict] = {}
    chunks: list[str] = []

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
            if t in SKIP_TYPES:
                continue

            if t == "assistant":
                content = rec.get("message", {}).get("content") or []
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
                content = rec.get("message", {}).get("content")
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
                            if suffix and chunks:
                                last = chunks[-1]
                                if last.startswith(TOOL_HDR):
                                    chunks[-1] = last + suffix

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


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: filter-transcript.py <transcript.jsonl>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        return 1

    filters_dir = Path(__file__).parent / "filters"
    filters = load_filters(filters_dir)

    body, state = render_transcript(path, filters)

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
        f"raw_bytes={raw} output_bytes={output} saved_pct={saved_pct} "
        f"filters_loaded={len(filters)} -->\n"
    )
    sys.stdout.write(audit + body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
