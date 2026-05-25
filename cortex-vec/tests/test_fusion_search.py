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

    def search(self, query, n, where=None, synonym_weight=0.0):
        return _bm25_items()


def test_hybrid_merges_both(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec_items())
    monkeypatch.setattr(bm25, "BM25Index", _FakeBM25)
    out = fusion.search("nginx 憑證", n=5)
    ids = [o["id"] for o in out]
    assert ids[0] == "Notes/Nginx/cert-renew.md"  # in both streams -> top
    assert "Notes/Linux/oom.md" in ids            # bm25-only hit still surfaces
    assert out[0]["summary"] == "certbot"
    assert "score" in out[0]


def test_degrades_to_bm25_when_vector_raises(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    def _boom(*a, **k):
        raise RuntimeError("no OPENAI_API_KEY")
    monkeypatch.setattr(store, "vector_stream", _boom)
    monkeypatch.setattr(bm25, "BM25Index", _FakeBM25)
    out = fusion.search("oom", n=5)
    assert [o["id"] for o in out][0] in {"Notes/Nginx/cert-renew.md", "Notes/Linux/oom.md"}
    assert out  # still returns results via bm25 only


def test_no_bm25_flag(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec_items())
    monkeypatch.setattr(bm25, "BM25Index", _FakeBM25)
    out = fusion.search("nginx", n=5, use_bm25=False)
    assert [o["id"] for o in out] == ["Notes/Nginx/cert-renew.md"]


def test_degrades_to_bm25_when_no_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def _should_not_be_called(*a, **k):
        raise AssertionError("vector_stream must not be called when API key is absent")

    monkeypatch.setattr(store, "vector_stream", _should_not_be_called)
    monkeypatch.setattr(bm25, "BM25Index", _FakeBM25)
    out = fusion.search("oom", n=5)
    assert out  # bm25-only results
    assert "Notes/Linux/oom.md" in [o["id"] for o in out]


def test_score_is_vector_cosine_not_rrf(monkeypatch):
    # Regression: the output `score` must stay the vector cosine similarity
    # (0-1 scale that distill/broadcast dedup thresholds are calibrated for),
    # NOT the tiny RRF fusion score (~0.01). RRF only orders results.
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec_items())
    monkeypatch.setattr(bm25, "BM25Index", _FakeBM25)
    out = fusion.search("nginx 憑證", n=5)
    by_id = {o["id"]: o["score"] for o in out}
    # vector hit keeps its cosine similarity (0.9), not an RRF score
    assert by_id["Notes/Nginx/cert-renew.md"] == 0.9
    # bm25-only hit has no cosine score -> 0.0
    assert by_id["Notes/Linux/oom.md"] == 0.0
