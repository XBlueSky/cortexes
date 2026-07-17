"""Shared source model for Raw session records (map-first authority).

Every character of a Raw belongs to exactly one SourceSpan: a gap-free,
overlap-free partition of the decoded text. Content the parser cannot
classify safely becomes ambiguous/opaque spans instead of disappearing.
This module is the ONLY Raw parsing authority; raw_view renders its legacy
L1-L3 projections from these spans through an adapter.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 1
PARSER_VERSION = 1

TURN_HEADERS = ("### User", "### Claude")
_TOOL_HDR = "> [tool] "
_TOOL_NAME_RE = re.compile(r"^> \[tool\] \*\*([^*]+)\*\*")
_MARKER_RE = re.compile(r"^<!--\s*distilled:.*-->$")

# Review-obligation classes (consumed by raw_map / distill_plan):
# card alone suffices / complete preview suffices / always needs raw-span.
CARD_REVIEW_KINDS = frozenset({"blank", "turn_header", "output_open",
                               "output_close"})
PREVIEW_REVIEW_KINDS = frozenset({"frontmatter", "tool_header",
                                  "meta_trailer"})
SPAN_REVIEW_KINDS = frozenset({"prose", "output_body", "ambiguous", "opaque"})


class DecodeError(ValueError):
    def __init__(self, byte_offset: int):
        self.byte_offset = byte_offset
        super().__init__(f"invalid UTF-8 at byte {byte_offset}")


class PartitionError(AssertionError):
    pass


@dataclass(frozen=True)
class RawIdentity:
    raw_path: str
    file_sha256: str
    source_sha256: str
    schema_version: int
    parser_version: int
    byte_count: int
    char_count: int
    line_count: int

    def to_json(self) -> dict:
        return {
            "raw_path": self.raw_path,
            "file_sha256": self.file_sha256,
            "source_sha256": self.source_sha256,
            "schema_version": self.schema_version,
            "parser_version": self.parser_version,
            "byte_count": self.byte_count,
            "char_count": self.char_count,
            "line_count": self.line_count,
        }


@dataclass(frozen=True)
class SourceSpan:
    id: int
    kind: str
    char_start: int  # inclusive
    char_end: int    # exclusive
    line_start: int  # 1-based inclusive
    line_end: int    # 1-based inclusive
    confidence: str  # "high" | "medium" | "low"
    tool_name: str | None = None


def strip_state_marker(text: str) -> str:
    """Remove the ONE position-anchored distilled marker line, if present.

    Same anchoring rules as distill_queue: the first whole-line marker BEFORE
    the first turn/tool header (header convention), else the last non-empty
    line if it is a marker (EOF convention). Markers quoted inside the
    conversation stay put.
    """
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            continue
        if s in TURN_HEADERS:
            break
        if _MARKER_RE.match(s):
            return "\n".join(lines[:i] + lines[i + 1:])
    for i in range(len(lines) - 1, -1, -1):
        s = lines[i].strip()
        if not s:
            continue
        if _MARKER_RE.match(s):
            # Remove marker and preceding blank line if present
            if i > 0 and not lines[i - 1].strip():
                return "\n".join(lines[:i - 1] + lines[i + 1:])
            else:
                return "\n".join(lines[:i] + lines[i + 1:])
        break
    return text


def load(path) -> tuple:
    """Read a Raw; return (RawIdentity, decoded_text). Strict UTF-8."""
    data = Path(path).read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise DecodeError(e.start) from e
    source = strip_state_marker(text)
    ident = RawIdentity(
        raw_path=str(path),
        file_sha256=hashlib.sha256(data).hexdigest(),
        source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        schema_version=SCHEMA_VERSION,
        parser_version=PARSER_VERSION,
        byte_count=len(data),
        char_count=len(text),
        line_count=text.count("\n") + 1,
    )
    return ident, text


def _line_table(text: str) -> list:
    """[(char_start, char_end)] per line; each line owns its trailing \\n.
    A zero-width final line (text ending in \\n) is dropped so every span
    is non-empty."""
    table = []
    pos = 0
    while pos <= len(text):
        nl = text.find("\n", pos)
        if nl == -1:
            if pos < len(text):
                table.append((pos, len(text)))
            break
        table.append((pos, nl + 1))
        pos = nl + 1
    return table


def validate_partition(spans, text) -> None:
    pos = 0
    for k, s in enumerate(spans):
        if s.id != k or s.char_start != pos or s.char_end <= s.char_start:
            raise PartitionError(f"span {k} breaks partition at char {pos}")
        pos = s.char_end
    if pos != len(text):
        raise PartitionError(f"partition ends at {pos}, text is {len(text)}")


def parse(text: str) -> list:
    """Parse a Raw into a validated gap-free/overlap-free span partition.

    Rules (this docstring is the spec):
    1. Lines own their trailing \\n; the partition is built line-by-line via
       the line table, so gap-freeness holds by construction.
    2. A leading ``---`` line is frontmatter only if a closing ``---`` is
       found before any turn/tool header; otherwise it is not frontmatter.
    3. Inside a ```output wrapper, turn/tool strings are literal. The close
       fence is the first bare ``` line whose next non-blank line is a
       turn/tool header or EOF. Passing a boundary-looking literal line
       before the close degrades output_body confidence to medium.
    4. No close fence found: everything after output_open to EOF is opaque
       (confidence low).
    5. A run of blank lines is always its own blank span; never swallowed.
    6. A whole-line distilled marker outside the conversation is
       meta_trailer; a marker quoted inside the conversation stays prose.
    """
    lt = _line_table(text)
    n = len(lt)
    lines = []
    for a, b in lt:
        seg = text[a:b]
        lines.append(seg[:-1] if seg.endswith("\n") else seg)

    spans: list = []

    def emit(kind, lo, hi, confidence="high", tool_name=None):
        spans.append(SourceSpan(
            id=len(spans), kind=kind,
            char_start=lt[lo][0], char_end=lt[hi][1],
            line_start=lo + 1, line_end=hi + 1,
            confidence=confidence, tool_name=tool_name,
        ))

    def is_blank(k):
        return lines[k].strip() == ""

    def is_turn(k):
        return lines[k] in TURN_HEADERS

    def is_tool(k):
        return lines[k].startswith(_TOOL_HDR)

    def parse_output(open_i: int) -> int:
        """```output wrapper starting at open_i; returns next line index.

        Inside the wrapper, turn/tool strings are literal content. The close
        fence is the FIRST bare ``` whose next non-blank line is a turn/tool
        header or EOF. This is safe because of filter-transcript's emit
        invariant: every assistant text block is written with its own
        `### Claude` header (see render_transcript), and a tool chunk is
        flushed with a trailing newline before the next non-tool chunk, so a
        real close fence is ALWAYS followed (after blanks) by a `### Claude` /
        `### User` / `> [tool]` boundary -- assistant commentary after a tool
        result never trails the fence as bare prose. A boundary-looking literal
        inside the body (a meta-session quoting another transcript) degrades
        confidence to medium; no close at all makes the tail opaque. A
        hand-edited Raw with bare prose directly after a close fence would fall
        to one opaque span -- coverage-safe (validate_partition still holds),
        just coarser navigation for that non-emittable region."""
        body0 = open_i + 1
        close = None
        saw_literal_boundary = False
        j = body0
        while j < n:
            if lines[j].strip() == "```":
                k = j + 1
                while k < n and is_blank(k):
                    k += 1
                if k >= n or is_turn(k) or is_tool(k):
                    close = j
                    break
            elif is_turn(j) or is_tool(j):
                saw_literal_boundary = True
            j += 1
        emit("output_open", open_i, open_i)
        if close is None:
            if body0 < n:
                emit("opaque", body0, n - 1, confidence="low")
            return n
        conf = "medium" if saw_literal_boundary else "high"
        if close > body0:
            emit("output_body", body0, close - 1, confidence=conf)
        emit("output_close", close, close)
        return close + 1

    i = 0
    in_conversation = False

    if n and lines[0] == "---":
        j = 1
        while (j < n and lines[j] != "---"
               and not is_turn(j) and not is_tool(j)):
            j += 1
        if j < n and lines[j] == "---":
            emit("frontmatter", 0, j)
            i = j + 1

    while i < n:
        if is_blank(i):
            j = i
            while j + 1 < n and is_blank(j + 1):
                j += 1
            emit("blank", i, j)
            i = j + 1
        elif is_turn(i):
            in_conversation = True
            emit("turn_header", i, i)
            i += 1
        elif is_tool(i):
            in_conversation = True
            m = _TOOL_NAME_RE.match(lines[i])
            emit("tool_header", i, i, tool_name=m.group(1) if m else None)
            i += 1
            k = i
            while k < n and is_blank(k):
                k += 1
            if k < n and lines[k] == "```output":
                if k > i:
                    emit("blank", i, k - 1)
                i = parse_output(k)
            # no ```output: the blanks re-enter the main loop as blank spans
        elif _MARKER_RE.match(lines[i].strip()) and not in_conversation:
            emit("meta_trailer", i, i)
            i += 1
        else:
            j = i
            while (j + 1 < n and not is_blank(j + 1)
                   and not is_turn(j + 1) and not is_tool(j + 1)):
                j += 1
            emit("prose", i, j)
            i = j + 1

    # EOF marker convention: a whole-line marker as the very last span in
    # conversation is the state trailer, not prose.
    if spans and spans[-1].kind == "prose":
        last = spans[-1]
        seg_lines = text[last.char_start:last.char_end].split("\n")
        seg_lines = [x for x in seg_lines if x.strip()]
        if len(seg_lines) == 1 and _MARKER_RE.match(seg_lines[0].strip()):
            spans[-1] = SourceSpan(
                id=last.id, kind="meta_trailer",
                char_start=last.char_start, char_end=last.char_end,
                line_start=last.line_start, line_end=last.line_end,
                confidence="high")

    validate_partition(spans, text)
    return spans
