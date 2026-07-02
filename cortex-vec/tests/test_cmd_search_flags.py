from types import SimpleNamespace
from cortex_vec import store, fusion


def test_cmd_search_threads_rerank_graph(monkeypatch):
    captured = {}
    monkeypatch.setattr(fusion, "search",
                        lambda query, n=5, where=None, use_bm25=True, use_vector=True,
                               rerank=None, graph=None:
                        captured.update(rerank=rerank, graph=graph) or [])
    args = SimpleNamespace(query="q", repo=None, type=None, category=None, n=5,
                           no_bm25=False, no_vector=False, rerank=True, graph=True)
    store.cmd_search(args)
    assert captured["rerank"] is True
    assert captured["graph"] is True


def test_build_where_no_args_returns_none():
    """No filter args → None (no where clause sent to ChromaDB)."""
    assert store._build_where() is None


def test_build_where_repo_includes_notes_type():
    """--repo X must broaden to also let type=note pass through.

    Notes/ are cross-repo by design and must never be excluded by --repo.
    """
    assert store._build_where(repo="acme-web") == {
        "$or": [{"repo": "acme-web"}, {"type": "note"}]
    }


def test_build_where_repo_combined_with_category():
    """--repo + --category: the OR-widened repo clause AND-combined with category."""
    assert store._build_where(repo="X", category="DSM") == {
        "$and": [
            {"$or": [{"repo": "X"}, {"type": "note"}]},
            {"category": "DSM"},
        ]
    }


def test_build_where_type_only_unchanged():
    """--type X alone is unaffected by the fix."""
    assert store._build_where(type="note") == {"type": "note"}
