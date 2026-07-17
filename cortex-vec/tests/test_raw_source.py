"""Source-model tests: identity, dual hash, and the partition parser."""
import hashlib

import pytest

from cortex_vec import raw_source as rs


def _write(tmp_path, text, name="raw.md"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


BODY = "---\ntype: session\n---\n### User\n\nhi\n\n### Claude\n\nok\n"


def test_identity_fields(tmp_path):
    p = _write(tmp_path, BODY)
    ident, text = rs.load(p)
    assert text == BODY
    assert ident.raw_path == str(p)
    assert ident.file_sha256 == hashlib.sha256(BODY.encode()).hexdigest()
    assert ident.char_count == len(BODY)
    assert ident.byte_count == len(BODY.encode())
    assert ident.line_count == BODY.count("\n") + 1
    assert (ident.schema_version, ident.parser_version) == (1, 1)


def test_source_hash_ignores_eof_marker(tmp_path):
    marked = BODY + "\n<!-- distilled: 2026-07-16 → (no insight) -->\n"
    a, _ = rs.load(_write(tmp_path, BODY, "a.md"))
    b, _ = rs.load(_write(tmp_path, marked, "b.md"))
    assert a.file_sha256 != b.file_sha256
    assert a.source_sha256 == b.source_sha256


def test_source_hash_ignores_header_marker(tmp_path):
    marked = ("---\ntype: session\n---\n"
              "<!-- distilled: 2026-07-16 → Notes/X.md -->\n"
              "### User\n\nhi\n\n### Claude\n\nok\n")
    plain = "---\ntype: session\n---\n### User\n\nhi\n\n### Claude\n\nok\n"
    a, _ = rs.load(_write(tmp_path, plain, "a.md"))
    b, _ = rs.load(_write(tmp_path, marked, "b.md"))
    assert a.source_sha256 == b.source_sha256


def test_quoted_marker_in_body_is_not_stripped(tmp_path):
    quoted = BODY + "\n### Claude\n\n<!-- distilled: 2026-01-01 → X -->\nmore\n"
    ident, text = rs.load(_write(tmp_path, quoted))
    assert rs.strip_state_marker(text) == quoted  # in-conversation quote stays


def test_decode_error_reports_byte_offset(tmp_path):
    p = tmp_path / "bad.md"
    p.write_bytes(b"ok\xff\xfebad")
    with pytest.raises(rs.DecodeError) as e:
        rs.load(p)
    assert e.value.byte_offset == 2


def _reconstruct(spans, text):
    return "".join(text[s.char_start:s.char_end] for s in spans)


def _assert_partition(text):
    spans = rs.parse(text)
    assert _reconstruct(spans, text) == text
    pos = 0
    for k, s in enumerate(spans):
        assert s.id == k and s.char_start == pos and s.char_end > pos
        pos = s.char_end
    assert pos == len(text)
    return spans


def test_partition_basic_session():
    text = ("---\ntype: session\n---\n"
            "<!-- audit: x -->\n"
            "### User\n\n幫我看 diff\n\n"
            "### Claude\n\n先跑 git diff。\n\n"
            "> [tool] **Bash**: `git diff`\n"
            "```output\nfile changed\n+added line\n```\n"
            "### Claude\n\n改好了。\n")
    spans = _assert_partition(text)
    kinds = [s.kind for s in spans]
    assert kinds == ["frontmatter", "prose", "turn_header", "blank", "prose",
                     "blank", "turn_header", "blank", "prose", "blank",
                     "tool_header", "output_open", "output_body",
                     "output_close", "turn_header", "blank", "prose"]
    tool = spans[10]
    assert tool.tool_name == "Bash"


def test_partition_output_wrapper_and_blanks_covered():
    # ```output fences and blank lines between tool calls must be spans.
    text = ("> [tool] **Bash**: `true`\n\n\n"
            "> [tool] **Bash**: `ls`\n"
            "```output\nok\n```\n")
    spans = _assert_partition(text)
    kinds = [s.kind for s in spans]
    assert kinds == ["tool_header", "blank", "tool_header",
                     "output_open", "output_body", "output_close"]


def test_partition_nested_balanced_fence():
    text = ("### Claude\n\n讀檔。\n\n"
            "> [tool] **Read**: `foo.md`\n"
            "```output\nintro\n```python\ncode = 1\n```\noutro\n```\n"
            "### Claude\n\ndone\n")
    spans = _assert_partition(text)
    body = [s for s in spans if s.kind == "output_body"][0]
    assert text[body.char_start:body.char_end] == (
        "intro\n```python\ncode = 1\n```\noutro\n")


def test_partition_bare_fence_body():
    text = ("> [tool] **Bash**: `cat x`\n"
            "```output\n```\nraw fence content\n```\n```\n"
            "> [tool] **Bash**: `echo done`\n"
            "```output\nok\n```\n")
    spans = _assert_partition(text)
    bodies = [text[s.char_start:s.char_end]
              for s in spans if s.kind == "output_body"]
    assert bodies == ["```\nraw fence content\n```\n", "ok\n"]


def test_partition_literal_turn_header_inside_output():
    # meta-session case: output quotes "### Claude" literally; the real
    # close comes later. Body keeps the literal; confidence degrades.
    text = ("> [tool] **Read**: `other-raw.md`\n"
            "```output\nquoted transcript:\n### Claude\n\nquoted prose\n```\n"
            "### Claude\n\nreal turn\n")
    spans = _assert_partition(text)
    body = [s for s in spans if s.kind == "output_body"][0]
    assert "### Claude" in text[body.char_start:body.char_end]
    assert body.confidence == "medium"
    assert [s.kind for s in spans].count("turn_header") == 1


def test_partition_unterminated_output_is_opaque():
    text = ("> [tool] **Bash**: `cat x`\n"
            "```output\nno close fence here\nstill going\n")
    spans = _assert_partition(text)
    kinds = [s.kind for s in spans]
    assert kinds == ["tool_header", "output_open", "opaque"]
    assert spans[-1].confidence == "low"


def test_partition_empty_and_tiny():
    assert rs.parse("") == []
    _assert_partition("\n")
    _assert_partition("x")
    _assert_partition("### User")


def test_partition_eof_marker_is_meta_trailer():
    text = BODY + "\n<!-- distilled: 2026-07-16 → (no insight) -->\n"
    spans = _assert_partition(text)
    assert spans[-1].kind == "meta_trailer" or spans[-2].kind == "meta_trailer"


def test_partition_unclosed_frontmatter_not_swallowed():
    text = "---\ntype: session\n### User\n\nhi\n"
    spans = _assert_partition(text)
    assert spans[0].kind != "frontmatter"
    assert "turn_header" in [s.kind for s in spans]


def test_partition_prose_after_tool_keeps_own_turn_header():
    # Real filter-transcript emit shape: assistant commentary AFTER a tool
    # result is written with its OWN "### Claude" header, never as bare prose
    # trailing the close fence. So the close rule (next non-blank is a
    # boundary) resolves correctly and no opaque span swallows the next turn.
    text = ("### Claude\n\n先跑指令。\n\n"
            "> [tool] **Bash**: `ls`\n```output\na.txt\n```\n\n"
            "### Claude\n\n結果如上。\n\n"
            "### User\n\n謝謝\n")
    spans = _assert_partition(text)
    kinds = [s.kind for s in spans]
    assert "opaque" not in kinds
    assert kinds.count("turn_header") == 3
    body = [s for s in spans if s.kind == "output_body"][0]
    assert body.confidence == "high"
    assert text[body.char_start:body.char_end] == "a.txt\n"


def test_validate_partition_raises_on_gap():
    text = "abcdef"
    incomplete = [rs.SourceSpan(0, "prose", 0, 2, 1, 1, "high")]
    with pytest.raises(rs.PartitionError):
        rs.validate_partition(incomplete, text)
