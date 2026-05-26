from cortex_vec import fusion, store, bm25, graph


def _vec():
    return [
        {"id": "a.md", "score": 0.9, "title": "A", "type": "note", "repo": "",
         "category": "", "tags": "", "summary": ""},
    ]


class _NoBM25:
    def __init__(self, *a, **k): pass
    def load(self): pass
    def search(self, *a, **k): return []


def test_graph_introduces_wikilink_neighbor(monkeypatch):
    # vector finds only a.md; a.md wikilinks to z.md (which vector/bm25 missed).
    # Graph (as a 3rd RRF stream) should surface z.md, with display from graph meta.
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    adjacency = {"a.md": {"z.md"}, "z.md": {"a.md"}}
    meta = {"z.md": {"id": "z.md", "title": "Z linked", "type": "note", "repo": "",
                     "category": "", "tags": "", "summary": "wiki neighbor"}}
    monkeypatch.setattr(graph, "build_graph", lambda vault: (adjacency, meta))
    monkeypatch.setattr(fusion, "get_vault_path", lambda: "/fake/vault", raising=False)

    out = fusion.search("q", n=5, graph=True)
    ids = [o["id"] for o in out]
    assert "a.md" in ids                              # original vector hit stays
    assert "z.md" in ids                              # wikilink-neighbor introduced
    z = next(o for o in out if o["id"] == "z.md")
    assert z["title"] == "Z linked"                   # display sourced from graph meta


def test_graph_off_by_default(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    called = {"build": False}

    def _build(vault):
        called["build"] = True
        return {}, {}

    monkeypatch.setattr(graph, "build_graph", _build)
    fusion.search("q", n=2)  # graph defaults off
    assert called["build"] is False


def test_graph_degrades_when_vault_unconfigured(monkeypatch):
    import sys as _sys
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)

    def _exit():
        _sys.exit(1)  # mimics get_vault_path on missing config

    monkeypatch.setattr(fusion, "get_vault_path", _exit, raising=False)
    out = fusion.search("q", n=2, graph=True)   # must NOT raise SystemExit
    assert [o["id"] for o in out]               # still returns vector results
