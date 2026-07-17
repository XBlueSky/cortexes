"""Bounded-page plumbing shared by raw-map / raw-span / distill-plan.

page_chars counts the FINAL emitted stdout including print's trailing
newline: len(render_page(obj)) + 1. Because the object embeds its own
page_chars and the post-charge session counter, the size is resolved by
fixpoint iteration (monotone in digit width, so it converges).
"""
from __future__ import annotations

import base64
import json
import sys

PAGE_BUDGET_DEFAULT = 12000
SESSION_BUDGET_DEFAULT = 100000
CONTROL_RESERVE = 2048


class PageError(Exception):
    def __init__(self, code: str, **detail):
        self.code = code
        self.detail = detail
        super().__init__(code)


def render_page(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def encode_cursor(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str, expect_kind: str, identity) -> dict:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
    except Exception:
        raise PageError("CURSOR_MISMATCH", reason="undecodable cursor")
    if not (isinstance(payload, dict)
            and payload.get("k") == expect_kind
            and payload.get("s") == identity.schema_version
            and payload.get("p") == identity.parser_version
            and payload.get("f") == identity.file_sha256[:16]):
        raise PageError("CURSOR_MISMATCH",
                        reason="cursor is stale or belongs to another raw")
    return payload


def finalize_page(build, used_before: int):
    """Resolve build(page_chars, used_after) -> obj to a size fixpoint."""
    guess = 0
    for _ in range(8):
        obj = build(guess, used_before + guess)
        actual = len(render_page(obj)) + 1
        if actual == guess:
            return obj, actual
        guess = actual
    raise PageError("PAGE_BUDGET_TOO_SMALL",
                    reason="page accounting did not converge")


def emit(obj) -> None:
    print(render_page(obj))


def emit_error(code: str, **detail) -> None:
    emit({"error": code, **detail})
    sys.exit(2)
