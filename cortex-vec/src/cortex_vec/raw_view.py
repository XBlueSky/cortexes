"""Deterministic projection of a Raw session record for distill consumption.

Segments a Raw into meta / prose / tool blocks, then renders a budget-bounded
view (L0..L3) that keeps all analysis prose while eliding the verbatim tool
output that dominates byte-mass but carries little distill signal. Every
elision leaves a `(raw Lx-Ly)` anchor so the main session can Read the exact
span on demand. Pure functions only — no I/O, no config-file access.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import raw_source as _src


@dataclass(frozen=True)
class Block:
    kind: str  # "meta" | "prose" | "tool"
    lines: tuple[str, ...]
    start: int  # 1-based first source line
    end: int    # 1-based last source line (inclusive)
    tool_name: str | None = None
    header: str | None = None
    out_lines: tuple[str, ...] | None = None
    out_start: int | None = None  # 1-based first output-body line
    out_end: int | None = None    # 1-based last output-body line


def _span_lines(text: str, s) -> list:
    seg = text[s.char_start:s.char_end]
    if seg.endswith("\n"):
        seg = seg[:-1]
    return seg.split("\n")


def parse_blocks(text: str) -> list:
    """Legacy Block view rendered FROM the shared source model.

    raw_source.parse is the single parsing authority; this adapter folds its
    span partition back into the meta/prose/tool Block shape the L1-L3
    renderer consumes. Wrapper fences and inter-tool blanks have no Block
    representation (same as the historical parser) — coverage lives in the
    span layer, not here.
    """
    spans = _src.parse(text)
    blocks: list = []
    prose: list = []
    prose_start = None  # 1-based line

    def flush():
        if prose:
            blocks.append(Block("prose", tuple(prose), prose_start,
                                prose_start + len(prose) - 1))
            prose.clear()

    i = 0
    n = len(spans)
    # meta region: spans before the first turn_header / tool_header
    meta_end = 0
    while meta_end < n and spans[meta_end].kind not in ("turn_header",
                                                        "tool_header"):
        meta_end += 1
    if meta_end:
        last = spans[meta_end - 1]
        lines = []
        for s in spans[:meta_end]:
            lines.extend(_span_lines(text, s))
        blocks.append(Block("meta", tuple(lines), 1, last.line_end))
        i = meta_end

    while i < n:
        s = spans[i]
        if s.kind == "tool_header":
            flush()
            out_lines = out_start = out_end = None
            j = i + 1
            # Skip any blank spans after the header (they have no Block
            # representation, matching the historical parser), then look for
            # the ```output wrapper at the advanced position.
            while j < n and spans[j].kind == "blank":
                j += 1
            if j < n and spans[j].kind == "output_open":
                j += 1
                if j < n and spans[j].kind == "output_body":
                    out_lines = tuple(_span_lines(text, spans[j]))
                    out_start, out_end = spans[j].line_start, spans[j].line_end
                    j += 1
                if j < n and spans[j].kind == "output_close":
                    j += 1
            hdr = _span_lines(text, s)[0]
            blocks.append(Block("tool", (hdr,), s.line_start, s.line_end,
                                tool_name=s.tool_name or "?", header=hdr,
                                out_lines=out_lines, out_start=out_start,
                                out_end=out_end))
            i = j
        elif s.kind == "opaque" and i and spans[i - 1].kind == "output_open":
            # unterminated output: legacy shape treated the tail as body
            prev = blocks[-1]
            blocks[-1] = Block("tool", prev.lines, prev.start, prev.end,
                               tool_name=prev.tool_name, header=prev.header,
                               out_lines=tuple(_span_lines(text, s)),
                               out_start=s.line_start, out_end=s.line_end)
            i += 1
        else:
            if not prose:
                prose_start = s.line_start
            prose.extend(_span_lines(text, s))
            i += 1
    flush()
    return blocks


VIEW_DEFAULTS = {
    "budget": 150000,
    "keep_output_tools": ("Agent", "Task"),
    "l3_prose_head_lines": 8,
    "l3_collapse_tool_run": 4,
}


def _elide_anchor(start: int, end: int) -> str:
    return f"[... elided {end - start + 1} lines (raw L{start}-L{end}) ...]"


def _tool_lines(b: Block, level: str, keep: set) -> list[str]:
    out = [b.header] if level == "L1" else [f"> [tool] {b.tool_name}"]
    if b.out_lines is not None:
        if level == "L1" and b.tool_name in keep:
            out.append("```output")
            out.extend(b.out_lines)
            out.append("```")
        else:
            out.append(_elide_anchor(b.out_start, b.out_end))
    return out


def _is_special_prose(line: str) -> bool:
    # ★ Insight callouts, table rows, and box-drawing separators are
    # insight-dense — keep them verbatim even in the L3 skeleton.
    return "★" in line or line.lstrip().startswith("|") or "─" in line


def _l3_prose_lines(b: Block, head: int) -> list[str]:
    # parse_blocks does NOT split prose on blank lines, so a callout usually
    # shares its Block with surrounding filler. Handle per-line: keep the first
    # `head` lines, then keep special lines verbatim while eliding contiguous
    # runs of non-special lines to anchors. (A block-level "keep whole if any
    # special line" check would defeat head-limiting on exactly these blocks.)
    n = len(b.lines)
    if n <= head:
        return list(b.lines)
    out = list(b.lines[:head])
    i = head
    while i < n:
        if _is_special_prose(b.lines[i]):
            out.append(b.lines[i])
            i += 1
            continue
        j = i
        while j < n and not _is_special_prose(b.lines[j]):
            j += 1
        out.append(_elide_anchor(b.start + i, b.start + j - 1))
        i = j
    return out


def render(blocks: list[Block], level: str, cfg: dict) -> str:
    keep = set(cfg["keep_output_tools"])
    run_min = cfg["l3_collapse_tool_run"]
    head = cfg["l3_prose_head_lines"]
    out: list[str] = []
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b.kind == "meta":
            out.extend(b.lines)
        elif b.kind == "prose":
            out.extend(_l3_prose_lines(b, head) if level == "L3" else b.lines)
        else:  # tool
            if level == "L3" and run_min > 0:
                end = i
                while end + 1 < len(blocks) and blocks[end + 1].kind == "tool":
                    end += 1
                run_len = end - i + 1
                if run_len >= run_min:
                    a = blocks[i].start
                    z = blocks[end].out_end or blocks[end].end
                    out.append(f"[... {run_len} tool calls collapsed "
                               f"(raw L{a}-L{z}) ...]")
                    i = end + 1
                    continue
            out.extend(_tool_lines(b, level, keep))
        i += 1
    return "\n".join(out)


# Room reserved for the L3* truncation marker so it survives the [:budget]
# clamp at real budgets. The final [:budget] still guarantees output <= budget
# for ANY budget (the marker itself is clipped when budget is tiny).
_HARD_MARK_RESERVE = 200


def choose_level(text: str, cfg: dict) -> tuple[str, str]:
    budget = cfg["budget"]
    if len(text) <= budget:
        return "L0", text
    blocks = parse_blocks(text)
    rendered = ""
    for lvl in ("L1", "L2", "L3"):
        rendered = render(blocks, lvl, cfg)
        if len(rendered) <= budget:
            return lvl, rendered
    # Even L3 exceeds budget → hard-truncate with a RECOVERABLE pointer so the
    # dropped tail is not silently lost: cite the highest source line still
    # covered by a surviving anchor and the file's total line count, so the
    # operator can Read the un-projected tail directly.
    cut = max(0, budget - _HARD_MARK_RESERVE)
    body = rendered[:cut]
    total = text.count("\n") + 1
    covered = [int(m) for m in re.findall(r"raw L\d+-L(\d+)", body)]
    if covered:
        mark = (f"\n[... hard-truncated to budget: this projection covers "
                f"through ~raw L{max(covered)} of {total}; the tail is NOT "
                f"anchored — Read the source directly beyond ~L{max(covered)} ...]")
    else:
        mark = (f"\n[... hard-truncated to budget; source has {total} lines and "
                f"this projection is not anchored — Read the source directly ...]")
    return "L3*", (body + mark)[:budget]


def stat_sizes(text: str, cfg: dict) -> dict:
    blocks = parse_blocks(text)
    sizes = {"raw": len(text)}
    for lvl in ("L1", "L2", "L3"):
        sizes[lvl] = len(render(blocks, lvl, cfg))
    lvl, out = choose_level(text, cfg)
    sizes["chosen"] = lvl
    sizes["chosen_chars"] = len(out)
    return sizes


# --- CLI dispatch (called from cli.py, before the heavy store import) --------


def dispatch_raw_view(args) -> None:
    import json

    from .config import get_view_config

    cfg = get_view_config()
    if getattr(args, "budget", None):
        cfg["budget"] = args.budget
    with open(args.path, encoding="utf-8") as f:
        text = f.read()
    if getattr(args, "stat", False):
        print(json.dumps(stat_sizes(text, cfg), ensure_ascii=False))
        return
    lvl = getattr(args, "level", None)
    if lvl:
        out = text if lvl == "L0" else render(parse_blocks(text), lvl, cfg)
    else:
        _, out = choose_level(text, cfg)
    print(out)
