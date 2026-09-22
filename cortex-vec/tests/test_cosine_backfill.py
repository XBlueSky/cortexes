"""Cosine backfill for hits the vector top-n window missed.

Retrieval fuses three streams (vector + BM25 + wikilink graph) but `score`
only ever carried the vector cosine, so a page that entered through BM25 or
the graph reported 0.0 -- indistinguishable from "no overlap" to the
absolute-threshold consumers (distill / broadcast dedup). These tests pin the
backfill that gives every returned hit a cosine on the same scale.
"""
from pathlib import Path

import pytest

from cortex_vec import bm25, fusion, store

# Captured before conftest's autouse stub replaces it; this module is the one
# place that exercises the real implementation.
_REAL_COSINE_FOR = store.cosine_for


@pytest.fixture(autouse=True)
def _use_real_cosine_for(monkeypatch):
    monkeypatch.setattr(store, "cosine_for", _REAL_COSINE_FOR)


class _RecordingCol:
    """Fake Chroma collection that records the kwargs it was queried with."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


def _col_with(chunks):
    """chunks: list of (source_path, distance)."""
    return _RecordingCol({
        "documents": [["body" for _ in chunks]],
        "metadatas": [[{"source_path": sp} for sp, _ in chunks]],
        "distances": [[d for _, d in chunks]],
    })


def _install(monkeypatch, col):
    monkeypatch.setattr(store, "get_client", lambda: object())
    monkeypatch.setattr(store, "get_collection", lambda client: col)
    monkeypatch.setattr(store, "get_vault_path", lambda: Path("/vault"))


def test_cosine_for_returns_best_cosine_per_base_path(monkeypatch):
    """A page split into chunks reports its closest chunk, keyed by base path."""
    col = _col_with([
        ("/vault/Notes/Linux/oom.md", 0.60),
        ("/vault/Notes/Linux/oom.md", 0.27),
        ("/vault/Notes/Nginx/cert-renew.md", 0.50),
    ])
    _install(monkeypatch, col)
    got = store.cosine_for("oom dmesg",
                           ["Notes/Linux/oom.md", "Notes/Nginx/cert-renew.md"])
    assert got == {"Notes/Linux/oom.md": 0.73, "Notes/Nginx/cert-renew.md": 0.5}


def test_cosine_for_scopes_the_query_to_the_requested_paths(monkeypatch):
    """The backfill must not re-rank the whole collection, only the misses."""
    col = _col_with([("/vault/Notes/Linux/oom.md", 0.4)])
    _install(monkeypatch, col)
    store.cosine_for("oom", ["Notes/Linux/oom.md"])
    where = col.calls[0]["where"]
    assert where == {"source_path": {"$in": ["/vault/Notes/Linux/oom.md"]}}


def test_cosine_for_no_ids_issues_no_query(monkeypatch):
    col = _col_with([])
    _install(monkeypatch, col)
    assert store.cosine_for("anything", []) == {}
    assert col.calls == []


def _vec_items():
    return [
        {"id": "Notes/Nginx/cert-renew.md", "score": 0.9, "title": "Nginx 憑證",
         "type": "note", "repo": "", "category": "Nginx", "tags": "", "summary": "certbot"},
    ]


class _FakeBM25:
    def __init__(self, *a, **k):
        pass

    def load(self):
        pass

    def search(self, query, n, where=None, synonym_weight=0.0):
        return [
            {"id": "Notes/Nginx/cert-renew.md", "score": 7.2, "title": "Nginx 憑證",
             "type": "note", "repo": "", "category": "Nginx", "tags": "", "summary": "certbot"},
            {"id": "Notes/Linux/oom.md", "score": 3.1, "title": "Linux OOM",
             "type": "note", "repo": "", "category": "Linux", "tags": "", "summary": "oom"},
        ]


def test_bm25_only_hit_reports_a_real_cosine(monkeypatch):
    """The whole point: a BM25-only hit no longer reports a bogus 0.0."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec_items())
    monkeypatch.setattr(bm25, "BM25Index", _FakeBM25)
    monkeypatch.setattr(store, "cosine_for",
                        lambda q, ids: {"Notes/Linux/oom.md": 0.73})
    out = fusion.search("nginx 憑證", n=5)
    by_id = {o["id"]: o["score"] for o in out}
    assert by_id["Notes/Linux/oom.md"] == 0.73
    assert by_id["Notes/Nginx/cert-renew.md"] == 0.9  # vector cosine untouched


def test_backfill_asks_only_for_docs_without_a_cosine(monkeypatch):
    """Docs the vector stream already scored must not be re-queried."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec_items())
    monkeypatch.setattr(bm25, "BM25Index", _FakeBM25)
    asked = []

    def _spy(query, ids):
        asked.append(list(ids))
        return {}

    monkeypatch.setattr(store, "cosine_for", _spy)
    fusion.search("nginx 憑證", n=5)
    assert asked == [["Notes/Linux/oom.md"]]


def test_backfill_failure_degrades_to_zero(monkeypatch):
    """A broken backfill must not take the whole query down with it."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec_items())
    monkeypatch.setattr(bm25, "BM25Index", _FakeBM25)

    def _boom(query, ids):
        raise RuntimeError("chroma unavailable")

    monkeypatch.setattr(store, "cosine_for", _boom)
    out = fusion.search("nginx 憑證", n=5)
    by_id = {o["id"]: o["score"] for o in out}
    assert by_id["Notes/Linux/oom.md"] == 0.0
    assert by_id["Notes/Nginx/cert-renew.md"] == 0.9


def test_no_backfill_without_api_key(monkeypatch):
    """No embeddings available -> no vector path at all, so never call out."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(bm25, "BM25Index", _FakeBM25)

    def _should_not_be_called(*a, **k):
        raise AssertionError("cosine_for must not run without an API key")

    monkeypatch.setattr(store, "cosine_for", _should_not_be_called)
    out = fusion.search("oom", n=5)
    assert out
