"""raw-map: bounded navigation cards over the source partition.

Navigation, not judgment: cards expose kind/coordinates/size/preview/
deterministic lexical anchors. Emitting a card auto-reviews only the
structural classes (CARD_REVIEW_KINDS, and PREVIEW kinds when the preview
is complete); prose/output_body/ambiguous/opaque always need raw-span.
"""
from __future__ import annotations

import re

from . import distill_plan as dp
from . import raw_source as rs
from .raw_page import (PAGE_BUDGET_DEFAULT, PageError, decode_cursor,
                       emit, emit_error, encode_cursor, finalize_page,
                       render_page)

PREVIEW_CHARS = 160
_ISSUE_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d{3,7}\b")
_URL_RE = re.compile(r"https?://\S+")


def lexical_anchors(text: str, limit: int = 8) -> list:
    out, seen = [], set()
    for rx in (_ISSUE_RE, _URL_RE):
        for m in rx.finditer(text):
            v = m.group(0)
            if v not in seen:
                seen.add(v)
                out.append(v)
                if len(out) >= limit:
                    return out
    return out


def build_card(span, text: str, preview_chars: int = PREVIEW_CHARS) -> dict:
    seg = text[span.char_start:span.char_end]
    if span.kind == "blank":
        preview, complete = "", True
    else:
        preview = seg[:preview_chars]
        complete = len(preview) == len(seg)
    card = {
        "span_id": span.id,
        "kind": span.kind,
        "confidence": span.confidence,
        "char_start": span.char_start,
        "char_end": span.char_end,
        "line_start": span.line_start,
        "line_end": span.line_end,
        "source_chars": span.char_end - span.char_start,
        "preview": preview,
        "preview_complete": complete,
    }
    if span.tool_name:
        card["tool_name"] = span.tool_name
    ax = lexical_anchors(seg)
    if ax:
        card["lexical_anchors"] = ax
    return card


def _auto_reviewed(span, card) -> bool:
    if span.kind in rs.CARD_REVIEW_KINDS:
        return True
    return span.kind in rs.PREVIEW_REVIEW_KINDS and card["preview_complete"]


def _cursor(identity, next_index: int) -> str:
    return encode_cursor({"k": "map", "s": identity.schema_version,
                          "p": identity.parser_version,
                          "f": identity.file_sha256[:16], "i": next_index})


def dispatch(args) -> None:
    try:
        _dispatch(args)
    except PageError as e:
        emit_error(e.code, **e.detail)


def _dispatch(args) -> None:
    max_chars = getattr(args, "max_chars", None) or PAGE_BUDGET_DEFAULT
    state, ident, text, spans = dp.load_for_page(args.plan_id, args.path)
    start = 0
    if getattr(args, "cursor", None):
        start = decode_cursor(args.cursor, "map", ident)["i"]
    if start > len(spans):
        raise PageError("CURSOR_MISMATCH", reason="cursor beyond span count")

    find = getattr(args, "find", None)
    find_matches = None
    if find:
        find_matches = []
        pos = text.find(find)
        while pos != -1 and len(find_matches) < 50:
            for s in spans:
                if s.char_start <= pos < s.char_end \
                        and s.id not in find_matches:
                    find_matches.append(s.id)
                    break
            pos = text.find(find, pos + 1)

    used_before = state["session_used_chars"]
    budget = state["session_budget"] - dp.CONTROL_RESERVE

    def envelope(cards, next_index, page_chars, used_after):
        obj = {
            "schema_version": rs.SCHEMA_VERSION,
            "raw_identity": ident.to_json(),
            "plan_id": state["plan_id"],
            "cards": cards,
            "page_chars": page_chars,
            "session_used_chars": used_after,
            "session_remaining_chars": max(0, budget - used_after),
            "map_coverage": {"next_index": max(state["map_next_index"],
                                               next_index),
                             "span_count": len(spans)},
            "next_cursor": (_cursor(ident, next_index)
                            if next_index < len(spans) else None),
            "budget_status": "ok",
        }
        if find_matches is not None:
            obj["find_matches"] = find_matches
        return obj

    cards: list = []
    idx = start
    final_obj = None
    final_chars = None
    while idx < len(spans):
        cards.append(build_card(spans[idx], text))
        try:
            obj, chars = finalize_page(
                lambda pc, ua, c=list(cards), nx=idx + 1:
                envelope(c, nx, pc, ua), used_before)
        except PageError:
            obj, chars = None, max_chars + 1
        if chars > max_chars:
            cards.pop()
            break
        final_obj, final_chars = obj, chars
        idx += 1
    if final_obj is None:
        if start >= len(spans):
            # Empty tail page (empty Raw, or a cursor already at span_count):
            # still bounded -- if even the empty envelope exceeds the budget,
            # the budget is too small to represent a page at all.
            obj, chars = finalize_page(
                lambda pc, ua: envelope([], start, pc, ua), used_before)
            if chars > max_chars:
                raise PageError("PAGE_BUDGET_TOO_SMALL", max_chars=max_chars,
                                reason="empty page envelope exceeds budget")
            final_obj, final_chars = obj, chars
        else:
            raise PageError("PAGE_BUDGET_TOO_SMALL",
                            span_id=spans[start].id, max_chars=max_chars)

    dp.charge_and_save(state, final_chars)
    auto = [[spans[k].char_start, spans[k].char_end]
            for k in range(start, idx)
            if _auto_reviewed(spans[k], build_card(spans[k], text))]
    dp.mark_map_progress(state, idx, auto)
    assert len(render_page(final_obj)) + 1 == final_chars
    emit(final_obj)
