from cortex_vec import fusion, store, bm25, rerank


def _vec(): return [
    {"id": "a", "score": 0.9, "title": "A", "type": "note", "repo": "",
     "category": "", "tags": "", "summary": ""},
    {"id": "b", "score": 0.5, "title": "B", "type": "note", "repo": "",
     "category": "", "tags": "", "summary": ""},
]


class _NoBM25:
    def __init__(self, *a, **k): pass
    def load(self): pass
    def search(self, *a, **k): return []


def test_rerank_invoked_when_enabled(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    monkeypatch.setattr(rerank, "rerank", lambda query, results, model, window: list(reversed(results)))
    out = fusion.search("q", n=2, rerank=True)
    assert [o["id"] for o in out] == ["b", "a"]


def test_rerank_off_by_default(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    called = {"r": False}
    def _r(*a, **k):
        called["r"] = True
        return a[1]
    monkeypatch.setattr(rerank, "rerank", _r)
    fusion.search("q", n=2)
    assert called["r"] is False
