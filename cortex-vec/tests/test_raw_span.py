"""Span pages: exact reconstruction, no gap/overlap, 12K stdout cap."""
import json

import pytest

from cortex_vec import distill_plan as dp
from cortex_vec import raw_source as rs
from cortex_vec import raw_span as rsp


class Args:
    def __init__(self, **kw):
        kw.setdefault("cursor", None)
        kw.setdefault("span_id", None)
        kw.setdefault("max_chars", 12000)
        self.__dict__.update(kw)


LONG_LINE = "x" * 30000  # single line far beyond one page
RAW = ("### User\n\nquestion\n\n"
       "### Claude\n\n" + LONG_LINE + "\n")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    raw = tmp_path / "raw.md"
    raw.write_text(RAW, encoding="utf-8")
    st = dp.start_plan(str(raw), 12000, 200000)
    return raw, st


def _page(capsys, raw, st, **kw):
    rsp.dispatch(Args(path=str(raw), plan_id=st["plan_id"], **kw))
    out = capsys.readouterr().out
    assert len(out) <= kw.get("max_chars", 12000)
    return json.loads(out)


def test_long_single_line_pages_reconstruct_exactly(env, capsys):
    raw, st = env
    ident, text = rs.load(raw)
    target = [s for s in rs.parse(text) if s.kind == "prose"
              and s.char_end - s.char_start > 12000][0]
    got = []
    page = _page(capsys, raw, st, span_id=target.id)
    got.append(page["content"])
    while page["next_cursor"]:
        page = _page(capsys, raw, st, cursor=page["next_cursor"])
        got.append(page["content"])
    assert "".join(got) == text[target.char_start:target.char_end]
    assert all(p for p in got)


def test_reviewed_interval_tracks_pages(env, capsys):
    raw, st = env
    ident, text = rs.load(raw)
    target = [s for s in rs.parse(text) if s.kind == "prose"][0]
    _page(capsys, raw, st, span_id=target.id)
    st2 = dp._load_by_plan_id(st["plan_id"])
    assert dp._covered(st2["reviewed"], target.char_start,
                       target.char_start + 1)


def test_unknown_span_id_rejected(env, capsys):
    raw, st = env
    with pytest.raises(SystemExit):
        _page(capsys, raw, st, span_id=99999)


def test_tiny_budget_fails_explicitly(env, capsys):
    raw, st = env
    with pytest.raises(SystemExit):
        rsp.dispatch(Args(path=str(raw), plan_id=st["plan_id"],
                          span_id=0, max_chars=50))
    out = capsys.readouterr().out
    assert json.loads(out)["error"] == "PAGE_BUDGET_TOO_SMALL"
