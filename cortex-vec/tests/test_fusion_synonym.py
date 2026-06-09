from cortex_vec import fusion, bm25


def test_bm25_stream_passes_synonym_weight(monkeypatch):
    captured = {}

    class _Idx:
        def __init__(self, *a, **k):
            pass

        def load(self):
            pass

        def search(self, query, n, where=None, synonym_weight=0.0):
            captured["synonym_weight"] = synonym_weight
            return []

    monkeypatch.setattr(bm25, "BM25Index", _Idx)
    fusion._bm25_stream("q", 5, None, synonym_weight=0.7)
    assert captured["synonym_weight"] == 0.7
