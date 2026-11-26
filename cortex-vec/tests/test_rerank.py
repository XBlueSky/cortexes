import json

import httpx
import openai
import pytest

from cortex_vec import config, providers, rerank


class _FakeResp:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})})]


class _FakeClient:
    def __init__(self, content):
        self._content = content
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, **kwargs):
        return _FakeResp(self._content)


def _results():
    return [{"id": "a", "title": "A", "summary": ""}, {"id": "b", "title": "B", "summary": ""}]


def test_rerank_reorders_by_llm(monkeypatch):
    monkeypatch.setattr(openai, "OpenAI",
                        lambda: _FakeClient('[{"index": 1, "score": 9}, {"index": 0, "score": 2}]'))
    out = rerank.rerank("q", _results(), model="m", window=15)
    assert [r["id"] for r in out] == ["b", "a"]


def test_rerank_failure_returns_unchanged(monkeypatch):
    def _boom():
        raise RuntimeError("no key")
    monkeypatch.setattr(openai, "OpenAI", _boom)
    res = _results()
    assert rerank.rerank("q", res, model="m", window=15) == res


def test_rerank_empty_results():
    assert rerank.rerank("q", [], model="m", window=15) == []


def test_rerank_handles_fenced_json(monkeypatch):
    fenced = "```json\n[{\"index\": 1, \"score\": 9}, {\"index\": 0, \"score\": 1}]\n```"
    monkeypatch.setattr(openai, "OpenAI", lambda: _FakeClient(fenced))
    out = rerank.rerank("q", _results(), model="m", window=15)
    assert [r["id"] for r in out] == ["b", "a"]


def test_rerank_failure_leaves_a_note(monkeypatch):
    def _boom():
        raise RuntimeError("no key")
    monkeypatch.setattr(providers, "chat_client", _boom)
    res, notes = _results(), []
    assert rerank.rerank("q", res, model="m", window=15, notes=notes) == res
    assert notes == ["rerank failed (RuntimeError: no key); order unchanged"]


def test_rerank_uses_the_shared_chat_client(monkeypatch):
    monkeypatch.setattr(providers, "chat_client",
                        lambda: _FakeClient('[{"index": 1, "score": 9}, {"index": 0, "score": 2}]'))
    notes = []
    out = rerank.rerank("q", _results(), model="m", window=15, notes=notes)
    assert [r["id"] for r in out] == ["b", "a"] and notes == []


def test_a_negative_llm_score_still_ranks_above_the_results_it_left_out(monkeypatch):
    # The results the model left out go last whatever the others scored; they
    # used to count as -1.0, which put them above a score of -2.
    monkeypatch.setattr(providers, "chat_client", lambda: _FakeClient('[{"index": 1, "score": -2}]'))
    out = rerank.rerank("q", _results(), model="m", window=15)
    assert [r["id"] for r in out] == ["b", "a"]


def test_a_zero_window_does_not_call_the_chat_model(monkeypatch):
    def _no_chat():
        raise AssertionError("an empty window must not call the chat model")
    monkeypatch.setattr(providers, "chat_client", _no_chat)
    res, notes = _results(), []
    assert rerank.rerank("q", res, model="m", window=0, notes=notes) == res
    assert notes == []


GATEWAY = "https://llm.example.com/v1"
KEY = "k-test-123"


def _three():
    return [{"id": i, "title": i.upper(), "summary": ""} for i in ("a", "b", "c")]


@pytest.fixture
def endpoint_cfg(monkeypatch):
    monkeypatch.setenv("MY_RERANK_KEY", KEY)
    monkeypatch.setattr(config, "load_config", lambda: {"models": {"rerank": {
        "type": "endpoint", "base_url": GATEWAY, "api_key_env": "MY_RERANK_KEY"}}})

    def _no_chat():
        raise AssertionError("the endpoint type must not call the chat model")
    monkeypatch.setattr(providers, "chat_client", _no_chat)


@pytest.mark.parametrize("key", ["results", "data"])
def test_endpoint_rerank_reorders_by_relevance_score(endpoint_cfg, embedding_endpoint, key):
    seen = embedding_endpoint(lambda r: httpx.Response(200, json={key: [
        {"index": 0, "relevance_score": 0.1}, {"index": 1, "relevance_score": 0.9}]}))
    notes = []
    out = rerank.rerank("q", _results(), model="m", window=15, notes=notes)
    assert [r["id"] for r in out] == ["b", "a"] and notes == []
    body = json.loads(seen.requests[0].content)
    assert body == {"query": "q", "documents": ["A — ", "B — "]}    # the llm `model` argument is not sent


def test_negative_scores_still_rank_above_documents_the_endpoint_left_out(endpoint_cfg, embedding_endpoint):
    embedding_endpoint(lambda r: httpx.Response(200, json={"results": [
        {"index": 2, "relevance_score": -1.0}, {"index": 0, "relevance_score": -4.0}]}))
    out = rerank.rerank("q", _three(), model="m", window=15)
    assert [r["id"] for r in out] == ["c", "a", "b"]


def test_documents_left_out_keep_their_order_after_the_scored_ones(endpoint_cfg, embedding_endpoint):
    embedding_endpoint(lambda r: httpx.Response(200, json={"results": [{"index": 2, "relevance_score": 0.5}]}))
    out = rerank.rerank("q", _three() + [{"id": "d", "title": "D", "summary": ""}], model="m", window=3)
    assert [r["id"] for r in out] == ["c", "a", "b", "d"]          # d is past the window: untouched


def test_a_failed_endpoint_rerank_keeps_the_order_and_its_note_hides_the_key(endpoint_cfg, embedding_endpoint):
    embedding_endpoint(lambda r: httpx.Response(401, json={"error": f"bad key {KEY}"}))
    res, notes = _results(), []
    assert rerank.rerank("q", res, model="m", window=15, notes=notes) == res
    assert notes == ["rerank failed (RerankEndpointError: rerank endpoint returned HTTP 401 Unauthorized"
                     ": POST https://llm.example.com/v1/rerank); order unchanged"]


@pytest.mark.parametrize("key", ["results", "data"])
def test_an_endpoint_that_scores_nothing_is_a_failure_not_a_silent_no_op(endpoint_cfg, embedding_endpoint, key):
    embedding_endpoint(lambda r: httpx.Response(200, json={key: []}))
    res, notes = _results(), []
    assert rerank.rerank("q", res, model="m", window=15, notes=notes) == res
    assert notes == ["rerank failed (RerankEndpointError: rerank response scored none of the 2 documents)"
                     "; order unchanged"]


def test_endpoint_rerank_without_its_key_keeps_the_order(endpoint_cfg, embedding_endpoint, monkeypatch):
    seen = embedding_endpoint()
    monkeypatch.delenv("MY_RERANK_KEY")
    res, notes = _results(), []
    assert rerank.rerank("q", res, model="m", window=15, notes=notes) == res
    assert notes == ["rerank failed (RerankEndpointError: MY_RERANK_KEY not set); order unchanged"]
    assert seen.requests == []


def test_a_zero_window_sends_nothing_to_the_endpoint(endpoint_cfg, embedding_endpoint):
    seen = embedding_endpoint(lambda r: httpx.Response(200, json={"results": []}))
    res, notes = _results(), []
    assert rerank.rerank("q", res, model="m", window=0, notes=notes) == res
    assert seen.requests == [] and notes == []
