"""Characterization tests for the raw-view projection.

The Raw format is emitted by hooks/scripts/filter-transcript.py: tool output
lives in ```output fences whose body is verbatim and may contain nested ```
fences (Read of a .md, Edit diffs, meta-sessions quoting another Raw). A regex
parser closes on the first inner ``` and mis-segments; these tests pin the
state-machine behaviour, including graceful degradation on adversarial input.
"""

from cortex_vec import raw_view as rv


def test_parse_meta_prose_tool_basic():
    text = (
        "---\ntype: session\n---\n"
        "<!-- audit: x -->\n"
        "### User\n\n幫我看 diff\n\n"
        "### Claude\n\n先跑 git diff。\n\n"
        "> [tool] **Bash**: `git diff`\n"
        "```output\nfile changed\n+added line\n```\n"
        "### Claude\n\n改好了。\n"
    )
    blocks = rv.parse_blocks(text)
    kinds = [b.kind for b in blocks]
    assert kinds == ["meta", "prose", "tool", "prose"]
    tool = blocks[2]
    assert tool.tool_name == "Bash"
    assert tool.header == "> [tool] **Bash**: `git diff`"
    assert tool.out_lines == ("file changed", "+added line")
    # anchors point at the body's 1-based source line range
    assert text.split("\n")[tool.out_start - 1] == "file changed"
    assert text.split("\n")[tool.out_end - 1] == "+added line"


def test_parse_output_with_nested_balanced_fence():
    # Reading a markdown file: output body itself contains a ```python block.
    text = (
        "### Claude\n\n讀檔。\n\n"
        "> [tool] **Read**: `foo.md`\n"
        "```output\n"
        "intro\n"
        "```python\n"
        "code = 1\n"
        "```\n"
        "outro\n"
        "```\n"
        "### Claude\n\ndone\n"
    )
    blocks = rv.parse_blocks(text)
    tool = [b for b in blocks if b.kind == "tool"][0]
    # the WHOLE nested block is captured as output body, not truncated at inner ```
    assert tool.out_lines == ("intro", "```python", "code = 1", "```", "outro")
    # next block is the trailing prose, correctly re-synced
    assert blocks[-1].kind == "prose"
    assert "done" in "\n".join(blocks[-1].lines)


def test_parse_output_starting_with_bare_fence():
    # Real emit shape when a tool's OUTPUT is itself a bare-fence code block:
    # filter-transcript wraps text as ```output\n{text}\n```, so a text of
    # "```\nraw fence content\n```" yields TWO trailing fences (the content's
    # own close, then the output fence's close). The close = last ``` before
    # the next boundary, so the body is the 3 inner lines. This also exercises
    # the pathological "body starts with a bare ```" case.
    text = (
        "> [tool] **Bash**: `cat x`\n"
        "```output\n"
        "```\n"
        "raw fence content\n"
        "```\n"
        "```\n"
        "> [tool] **Bash**: `echo done`\n"
        "```output\nok\n```\n"
    )
    blocks = rv.parse_blocks(text)
    tools = [b for b in blocks if b.kind == "tool"]
    assert tools[0].out_lines == ("```", "raw fence content", "```")
    assert tools[1].out_lines == ("ok",)


def test_parse_tool_call_without_output():
    text = (
        "> [tool] **Bash**: `true`\n"
        "### Claude\n\nnext\n"
    )
    blocks = rv.parse_blocks(text)
    tool = blocks[0]
    assert tool.kind == "tool" and tool.out_lines is None


def test_parse_no_meta_when_starts_with_turn():
    text = "### User\n\nhi\n"
    blocks = rv.parse_blocks(text)
    assert [b.kind for b in blocks] == ["prose"]


def _cfg(**over):
    c = dict(rv.VIEW_DEFAULTS)
    c.update(over)
    return c


def test_render_l1_elides_bash_keeps_agent():
    text = (
        "> [tool] **Bash**: `ls`\n```output\na\nb\nc\n```\n"
        "> [tool] **Agent**: `review`\n```output\nfinding: real bug\n```\n"
    )
    out = rv.render(rv.parse_blocks(text), "L1", _cfg())
    assert "> [tool] **Bash**: `ls`" in out       # header kept verbatim
    assert "\na\nb\nc\n" not in out                # bash output elided
    assert "[... elided 3 lines (raw L3-L5) ...]" in out
    assert "finding: real bug" in out              # Agent output kept


def test_render_l2_elides_all_and_names_headers():
    text = (
        "### Claude\n\n分析文字保留\n\n"
        "> [tool] **Agent**: `review`\n```output\nfinding\n```\n"
    )
    out = rv.render(rv.parse_blocks(text), "L2", _cfg())
    assert "分析文字保留" in out                    # prose kept in L2
    assert out.count("> [tool] Agent") == 1         # header reduced to name
    assert "`review`" not in out                    # args dropped
    assert "finding" not in out                     # even Agent output elided


def test_render_l3_collapses_tool_runs():
    text = "### Claude\n\nstart\n\n" + "".join(
        f"> [tool] **Bash**: `cmd{i}`\n```output\nout{i}\n```\n" for i in range(5)
    )
    out = rv.render(rv.parse_blocks(text), "L3", _cfg())
    assert "start" in out
    assert "tool calls collapsed" in out            # 5 ≥ 4 → collapsed
    assert "cmd0" not in out and "cmd4" not in out


def test_render_l3_keeps_callouts_headlimits_long_prose():
    long_prose = "\n".join(f"line {i}" for i in range(20))
    text = f"### Claude\n\n{long_prose}\n\n★ Insight 這段是關鍵\n"
    out = rv.render(rv.parse_blocks(text), "L3", _cfg(l3_prose_head_lines=3))
    assert "★ Insight 這段是關鍵" in out             # callout kept whole
    assert "line 0" in out and "line 19" not in out  # long prose head-limited
    assert "raw L" in out                            # anchor present


def test_choose_level_l0_when_small():
    text = "### User\n\nhi\n"
    lvl, out = rv.choose_level(text, _cfg(budget=10_000))
    assert lvl == "L0" and out == text


def test_choose_level_steps_down_to_fit_budget():
    # A file too big for L0/L1 but small enough after eliding output.
    big = "x" * 500
    text = "### Claude\n\nkeep me\n\n" + "".join(
        f"> [tool] **Bash**: `c{i}`\n```output\n{big}\n```\n" for i in range(5)
    )
    lvl, out = rv.choose_level(text, _cfg(budget=1500))
    assert lvl in ("L1", "L2", "L3")
    assert len(out) <= 1500
    assert "keep me" in out            # analysis prose survived


def test_choose_level_hard_guarantee():
    # Force the L3* hard-truncation path: L3 keeps ★callout lines verbatim and
    # cannot collapse them, so a wall of callouts exceeds a tiny budget even at
    # L3 and the backstop must still cap the output. (A wall of tool headers
    # can't exercise this path — L3 collapses consecutive tool runs to one line.)
    text = "### Claude\n\n" + "\n".join(f"★ insight {i}" for i in range(500))
    lvl, out = rv.choose_level(text, _cfg(budget=500))
    assert len(out) <= 500             # hard guarantee holds
    assert lvl == "L3*"                # marked as hard-truncated


def test_stat_sizes_shape():
    text = "### Claude\n\nhi\n\n> [tool] **Bash**: `ls`\n```output\na\nb\n```\n"
    st = rv.stat_sizes(text, _cfg(budget=20))
    assert set(st) == {"raw", "L1", "L2", "L3", "chosen", "chosen_chars"}
    assert st["raw"] == len(text)
    assert st["L1"] >= st["L2"] >= st["L3"]     # ladder is monotonic non-increasing
    assert st["chosen_chars"] <= 20


def test_get_view_config_defaults_when_no_file(monkeypatch, tmp_path):
    from cortex_vec import config
    monkeypatch.setattr(config, "CORTEX_CONFIG", tmp_path / "nope.json")
    vc = config.get_view_config()
    assert vc["budget"] == rv.VIEW_DEFAULTS["budget"]
    assert vc["keep_output_tools"] == rv.VIEW_DEFAULTS["keep_output_tools"]


def test_get_view_config_user_override(monkeypatch, tmp_path):
    import json
    from cortex_vec import config
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"distill": {"view": {"budget": 42}}}))
    monkeypatch.setattr(config, "CORTEX_CONFIG", p)
    assert config.get_view_config()["budget"] == 42


def test_dispatch_raw_view_stat_json(tmp_path, capsys):
    import json
    p = tmp_path / "r.md"
    p.write_text("### Claude\n\nhi\n\n> [tool] **Bash**: `ls`\n```output\na\n```\n",
                 encoding="utf-8")

    class A:
        path = str(p)
        budget = 30
        level = None
        stat = True
    rv.dispatch_raw_view(A())
    st = json.loads(capsys.readouterr().out)
    assert st["raw"] > 0 and st["chosen_chars"] <= 30


def test_choose_level_l3star_marker_is_recoverable():
    # L3 exceeds a small budget AND has elision anchors (collapse disabled), so
    # the L3* marker must cite the highest covered source line + total lines.
    tools = "".join(
        f"> [tool] **Bash**: `c{i}`\n```output\n" + "x\n" * 30 + "```\n"
        for i in range(40)
    )
    text = "### Claude\n\nstart\n\n" + tools
    lvl, out = rv.choose_level(text, _cfg(budget=400, l3_collapse_tool_run=999))
    assert lvl == "L3*"
    assert len(out) <= 400
    assert "hard-truncated to budget" in out
    assert "covers through ~raw L" in out   # recoverable pointer present
    assert " of " in out                     # total line count present


def test_parse_no_output_tool_then_blank_then_tool_folds_blank():
    # A no-output tool call, a blank line, then another tool: the blank must
    # NOT become a spurious prose Block between them (historical parser folded
    # inter-tool blanks away; the adapter must too).
    text = ("> [tool] **AAA**: `x`\n\n"
            "> [tool] **BBB**: `y`\n```output\nfoo\n```\n")
    blocks = rv.parse_blocks(text)
    assert [b.kind for b in blocks] == ["tool", "tool"]
    assert blocks[0].tool_name == "AAA" and blocks[0].out_lines is None
    assert blocks[1].tool_name == "BBB" and blocks[1].out_lines == ("foo",)


def test_parse_no_output_tool_then_blank_then_turn_anchor_start():
    # The prose Block after a no-output tool + blank must start at the turn
    # header line, not swallow the preceding blank (which would shift L3
    # anchors by one source line).
    text = "> [tool] **Bash**: `true`\n\n### Claude\n\nnext\n"
    blocks = rv.parse_blocks(text)
    assert [b.kind for b in blocks] == ["tool", "prose"]
    prose = blocks[1]
    assert prose.lines[0] == "### Claude"
    assert prose.start == 3
