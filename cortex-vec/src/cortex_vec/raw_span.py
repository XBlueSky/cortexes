"""raw-span: the ONLY reader that returns Raw original text to the session.

Pages are exact substrings of the immutable Raw, hard-capped at max_chars
of emitted stdout, with character-offset continuation for spans (or single
lines) larger than one page. No summarization, no projection, no verdicts.
"""
from __future__ import annotations

from . import distill_plan as dp
from . import raw_source as rs
from .raw_page import (PAGE_BUDGET_DEFAULT, PageError, decode_cursor,
                       emit, emit_error, encode_cursor, finalize_page,
                       render_page)


def dispatch(args) -> None:
    try:
        _dispatch(args)
    except PageError as e:
        emit_error(e.code, **e.detail)


def _dispatch(args) -> None:
    max_chars = getattr(args, "max_chars", None) or PAGE_BUDGET_DEFAULT
    state, ident, text, spans = dp.load_for_page(args.plan_id, args.path)

    if getattr(args, "cursor", None):
        payload = decode_cursor(args.cursor, "span", ident)
        span_id, offset = payload["id"], payload["o"]
    elif getattr(args, "span_id", None) is not None:
        span_id, offset = args.span_id, 0
    else:
        raise PageError("CURSOR_MISMATCH",
                        reason="need --span-id or --cursor")
    if not (0 <= span_id < len(spans)):
        raise PageError("CURSOR_MISMATCH", reason="unknown span id",
                        span_id=span_id)
    span = spans[span_id]
    seg = text[span.char_start:span.char_end]
    if not (0 <= offset < len(seg)):
        raise PageError("CURSOR_MISMATCH", reason="offset out of range")

    used_before = state["session_used_chars"]
    budget = state["session_budget"] - dp.CONTROL_RESERVE

    def envelope(take, page_chars, used_after):
        end = offset + take
        return {
            "schema_version": rs.SCHEMA_VERSION,
            "raw_identity": ident.to_json(),
            "plan_id": state["plan_id"],
            "span_id": span.id,
            "kind": span.kind,
            "char_start": span.char_start + offset,
            "char_end": span.char_start + end,
            "line_start": span.line_start,
            "line_end": span.line_end,
            "source_chars": len(seg),
            "content": seg[offset:end],
            "page_chars": page_chars,
            "session_used_chars": used_after,
            "session_remaining_chars": max(0, budget - used_after),
            "next_cursor": (encode_cursor(
                {"k": "span", "s": ident.schema_version,
                 "p": ident.parser_version,
                 "f": ident.file_sha256[:16],
                 "id": span.id, "o": end}) if end < len(seg) else None),
            "budget_status": "ok",
        }

    # binary-search the largest take whose FINAL stdout fits max_chars
    lo, hi = 0, len(seg) - offset
    best = None
    while lo < hi:
        mid = (lo + hi + 1) // 2
        try:
            obj, chars = finalize_page(
                lambda pc, ua, t=mid: envelope(t, pc, ua), used_before)
        except PageError:
            hi = mid - 1
            continue
        if chars <= max_chars:
            best = (obj, chars, mid)
            lo = mid
        else:
            hi = mid - 1
    if best is None:
        raise PageError("PAGE_BUDGET_TOO_SMALL", span_id=span.id,
                        max_chars=max_chars)
    obj, chars, take = best

    dp.charge_and_save(state, chars)
    dp.mark_reviewed(state, span.char_start + offset,
                     span.char_start + offset + take)
    assert len(render_page(obj)) + 1 == chars
    emit(obj)
