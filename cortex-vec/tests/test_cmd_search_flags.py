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
