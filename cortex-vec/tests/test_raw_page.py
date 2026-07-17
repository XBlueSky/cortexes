"""Cursor binding and fixpoint page accounting."""
import pytest

from cortex_vec import raw_page as rp
from cortex_vec import raw_source as rs


def _ident(tmp_path, text="### User\n\nhi\n"):
    p = tmp_path / "r.md"
    p.write_text(text, encoding="utf-8")
    ident, _ = rs.load(p)
    return ident


def test_cursor_roundtrip(tmp_path):
    ident = _ident(tmp_path)
    payload = {"k": "map", "s": ident.schema_version,
               "p": ident.parser_version, "f": ident.file_sha256[:16],
               "i": 7}
    c = rp.encode_cursor(payload)
    assert rp.decode_cursor(c, "map", ident) == payload


def test_cursor_rejects_foreign_raw(tmp_path):
    a = _ident(tmp_path)
    other = tmp_path / "other.md"
    other.write_text("### User\n\ndifferent\n", encoding="utf-8")
    b, _ = rs.load(other)
    c = rp.encode_cursor({"k": "map", "s": a.schema_version,
                          "p": a.parser_version,
                          "f": a.file_sha256[:16], "i": 0})
    with pytest.raises(rp.PageError) as e:
        rp.decode_cursor(c, "map", b)
    assert e.value.code == "CURSOR_MISMATCH"


def test_cursor_rejects_wrong_kind_and_garbage(tmp_path):
    ident = _ident(tmp_path)
    c = rp.encode_cursor({"k": "span", "s": 1, "p": 1,
                          "f": ident.file_sha256[:16], "i": 0})
    with pytest.raises(rp.PageError):
        rp.decode_cursor(c, "map", ident)
    with pytest.raises(rp.PageError):
        rp.decode_cursor("!!!not-base64!!!", "map", ident)


def test_finalize_page_fixpoint_converges():
    def build(page_chars, used_after):
        return {"page_chars": page_chars, "session_used_chars": used_after,
                "payload": "x" * 100}
    obj, actual = rp.finalize_page(build, used_before=99990)
    assert obj["page_chars"] == actual
    assert obj["session_used_chars"] == 99990 + actual
    assert actual == len(rp.render_page(obj)) + 1
