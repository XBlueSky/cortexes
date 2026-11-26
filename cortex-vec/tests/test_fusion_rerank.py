import json

import httpx
import pytest

from cortex_vec import fusion, store, bm25, rerank, config, providers


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
    monkeypatch.setattr(rerank, "rerank",
                        lambda query, results, model, window, notes=None: list(reversed(results)))
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


@pytest.mark.parametrize("cfg, expected", [
    ({}, "gpt-5.4-mini"),
    ({"models": {"chat": {"model": "my-chat-model"}}}, "my-chat-model"),
    ({"models": {"chat": {"model": "my-chat-model"}}, "retrieval": {"rerank_model": "pinned"}}, "pinned"),
])
def test_rerank_model_follows_chat_unless_retrieval_pins_one(monkeypatch, cfg, expected):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(config, "load_config", lambda: cfg)
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    seen = {}
    monkeypatch.setattr(rerank, "rerank",
                        lambda query, results, model, window, notes=None: seen.update(model=model) or results)
    fusion.search("q", n=2, rerank=True)
    assert seen["model"] == expected


def test_a_failed_rerank_keeps_the_order_and_reaches_the_search_notes(monkeypatch):
    def _boom():
        raise RuntimeError("no key")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    monkeypatch.setattr(providers, "chat_client", _boom)
    notes = []
    out = fusion.search("q", n=2, rerank=True, notes=notes)
    assert [o["id"] for o in out] == ["a", "b"]
    assert any("rerank failed" in n and "order unchanged" in n for n in notes)


def test_search_reranks_through_the_endpoint_when_config_turns_it_on(monkeypatch, embedding_endpoint):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(config, "load_config", lambda: {
        "retrieval": {"rerank": True},
        "models": {"rerank": {"type": "endpoint", "base_url": "https://llm.example.com/v1"}}})
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    seen = embedding_endpoint(lambda r: httpx.Response(200, json={"results": [
        {"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}]}))
    notes = []
    out = fusion.search("q", n=2, notes=notes)
    assert [o["id"] for o in out] == ["b", "a"] and notes == []
    assert json.loads(seen.requests[0].content)["documents"] == ["A — ", "B — "]
