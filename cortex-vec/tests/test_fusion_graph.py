from cortex_vec import fusion, store, bm25, graph


def _vec(): return [
    {"id": "a.md", "score": 0.9, "title": "A", "type": "note", "repo": "",
     "category": "", "tags": "", "summary": ""},
    {"id": "c.md", "score": 0.1, "title": "C", "type": "note", "repo": "",
     "category": "", "tags": "", "summary": ""},
]


class _NoBM25:
    def __init__(self, *a, **k): pass
    def load(self): pass
    def search(self, *a, **k): return []


def test_graph_boost_applied_when_enabled(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    monkeypatch.setattr(graph, "build_graph", lambda vault: {"a.md": {"c.md"}, "c.md": {"a.md"}})
    monkeypatch.setattr(fusion, "get_vault_path", lambda: "/fake/vault", raising=False)
    out = fusion.search("q", n=2, graph=True)
    assert [o["id"] for o in out][0] == "a.md"
    assert "c.md" in [o["id"] for o in out]


def test_graph_off_by_default(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    called = {"build": False}
    def _build(vault):
        called["build"] = True
        return {}
    monkeypatch.setattr(graph, "build_graph", _build)
    fusion.search("q", n=2)
    assert called["build"] is False


def test_graph_boost_degrades_when_vault_unconfigured(monkeypatch):
    import sys as _sys
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)

    def _exit():
        _sys.exit(1)  # mimics get_vault_path on missing config

    monkeypatch.setattr(fusion, "get_vault_path", _exit, raising=False)
    out = fusion.search("q", n=2, graph=True)   # must NOT raise SystemExit
    assert [o["id"] for o in out]               # still returns vector results
