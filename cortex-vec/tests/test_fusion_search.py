from cortex_vec import fusion, store, bm25


def _vec_items():
    return [
        {"id": "Notes/Nginx/cert-renew.md", "score": 0.9, "title": "Nginx 憑證",
         "type": "note", "repo": "", "category": "Nginx", "tags": "", "summary": "certbot"},
    ]


def _bm25_items():
    return [
        {"id": "Notes/Nginx/cert-renew.md", "score": 7.2, "title": "Nginx 憑證",
         "type": "note", "repo": "", "category": "Nginx", "tags": "", "summary": "certbot"},
        {"id": "Notes/Linux/oom.md", "score": 3.1, "title": "Linux OOM",
         "type": "note", "repo": "", "category": "Linux", "tags": "", "summary": "oom"},
    ]


class _FakeBM25:
    def __init__(self, *a, **k):
        pass

    def load(self):
        pass

    def search(self, query, n, where=None):
        return _bm25_items()


def test_hybrid_merges_both(monkeypatch):
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec_items())
    monkeypatch.setattr(bm25, "BM25Index", _FakeBM25)
    out = fusion.search("nginx 憑證", n=5)
    ids = [o["id"] for o in out]
    assert ids[0] == "Notes/Nginx/cert-renew.md"  # in both streams -> top
    assert "Notes/Linux/oom.md" in ids            # bm25-only hit still surfaces
    assert out[0]["summary"] == "certbot"
    assert "score" in out[0]


def test_degrades_to_bm25_when_vector_raises(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("no OPENAI_API_KEY")
    monkeypatch.setattr(store, "vector_stream", _boom)
    monkeypatch.setattr(bm25, "BM25Index", _FakeBM25)
    out = fusion.search("oom", n=5)
    assert [o["id"] for o in out][0] in {"Notes/Nginx/cert-renew.md", "Notes/Linux/oom.md"}
    assert out  # still returns results via bm25 only


def test_no_bm25_flag(monkeypatch):
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec_items())
    monkeypatch.setattr(bm25, "BM25Index", _FakeBM25)
    out = fusion.search("nginx", n=5, use_bm25=False)
    assert [o["id"] for o in out] == ["Notes/Nginx/cert-renew.md"]
