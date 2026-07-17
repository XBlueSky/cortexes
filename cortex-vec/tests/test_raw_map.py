"""Map pages: full traversal, 12K stdout cap, auto-review classes."""
import json

import pytest

from cortex_vec import distill_plan as dp
from cortex_vec import raw_map as rm
from cortex_vec import raw_page as rp
from cortex_vec import raw_source as rs


RAW = ("---\nrepo: cortex\n---\n"
       "### User\n\n處理 PROJ-4521\n\n"
       "### Claude\n\n分析在 src/x.py:12。\n\n"
       "> [tool] **Bash**: `git log`\n"
       "```output\n" + "log line\n" * 40 + "```\n")


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    raw = tmp_path / "raw.md"
    raw.write_text(RAW, encoding="utf-8")
    st = dp.start_plan(str(raw), 12000, 100000)
    return raw, st


def _page(capsys, raw, st, cursor=None, max_chars=12000, find=None):
    rm.dispatch(Args(path=str(raw), plan_id=st["plan_id"], cursor=cursor,
                     max_chars=max_chars, find=find))
    out = capsys.readouterr().out
    assert out.endswith("\n")
    assert len(out) <= max_chars
    return json.loads(out)


def test_full_traversal_covers_every_span(env, capsys):
    raw, st = env
    ident, text = rs.load(raw)
    total = len(rs.parse(text))
    seen = []
    cursor = None
    while True:
        page = _page(capsys, raw, st, cursor)
        seen.extend(c["span_id"] for c in page["cards"])
        if page["next_cursor"] is None:
            break
        cursor = page["next_cursor"]
    assert seen == list(range(total))
    st2 = dp._load_by_plan_id(st["plan_id"])
    assert st2["map_next_index"] == total


def test_small_budget_paginates_and_never_overflows(env, capsys):
    raw, st = env
    page = _page(capsys, raw, st, max_chars=3000)
    assert page["next_cursor"] is not None
    assert 1 <= len(page["cards"])


def test_lexical_anchors_and_find(env, capsys):
    raw, st = env
    page = _page(capsys, raw, st, find="PROJ-4521")
    assert page["find_matches"], "issue id should locate its span"
    anchors = [a for c in page["cards"]
               for a in c.get("lexical_anchors", [])]
    assert "PROJ-4521" in anchors


def test_card_review_classes_feed_reviewed_intervals(env, capsys):
    raw, st = env
    cursor = None
    while True:
        page = _page(capsys, raw, st, cursor)
        if page["next_cursor"] is None:
            break
        cursor = page["next_cursor"]
    st2 = dp._load_by_plan_id(st["plan_id"])
    payload = dp.status_payload(st2)
    # map complete, but prose/output_body still unreviewed
    assert payload["map_coverage_complete"] is True
    assert payload["no_insight_candidate_allowed"] is False
    assert payload["unreviewed_semantic_count"] >= 1


def test_ledger_charged_per_page(env, capsys):
    raw, st = env
    before = dp._load_by_plan_id(st["plan_id"])["session_used_chars"]
    page = _page(capsys, raw, st)
    after = dp._load_by_plan_id(st["plan_id"])["session_used_chars"]
    assert after - before == page["page_chars"]


def _tail_cursor(raw):
    ident, text = rs.load(raw)
    total = len(rs.parse(text))
    return rp.encode_cursor({"k": "map", "s": ident.schema_version,
                             "p": ident.parser_version,
                             "f": ident.file_sha256[:16], "i": total})


def test_empty_tail_page_is_bounded_and_terminal(env, capsys):
    raw, st = env
    page = _page(capsys, raw, st, cursor=_tail_cursor(raw))
    assert page["cards"] == []
    assert page["next_cursor"] is None


def test_empty_tail_page_too_small_budget_errors(env, capsys):
    raw, st = env
    with pytest.raises(SystemExit):
        rm.dispatch(Args(path=str(raw), plan_id=st["plan_id"],
                         cursor=_tail_cursor(raw), max_chars=50, find=None))
    out = capsys.readouterr().out
    assert json.loads(out)["error"] == "PAGE_BUDGET_TOO_SMALL"


def test_first_card_too_small_budget_errors(env, capsys):
    raw, st = env
    with pytest.raises(SystemExit):
        rm.dispatch(Args(path=str(raw), plan_id=st["plan_id"],
                         cursor=None, max_chars=50, find=None))
    out = capsys.readouterr().out
    assert json.loads(out)["error"] == "PAGE_BUDGET_TOO_SMALL"
