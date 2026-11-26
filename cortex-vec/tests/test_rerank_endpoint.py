"""The rerank endpoint type: the request it sends, the replies it accepts, how it fails. No socket is opened."""
import json

import httpx
import pytest

from cortex_vec.rerank_endpoint import RerankEndpointError, parse_rerank, score

GATEWAY = "https://llm.example.com/v1"
KEY = "k-test-123"
DOCS = ["A — a", "B — b"]
ONE = {"results": [{"index": 0, "relevance_score": 0.5}]}   # the smallest reply that is not a failure


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("MY_RERANK_KEY", KEY)


def _score(**overrides):
    kwargs = {"model": None, "base_url": GATEWAY, "api_key_env": "MY_RERANK_KEY", **overrides}
    return score("q", DOCS, **kwargs)


def _reply(payload):
    return lambda request: httpx.Response(200, json=payload)


@pytest.mark.parametrize("payload", [
    {"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.2}]},
    {"data": [{"index": 0, "relevance_score": 0.2}, {"index": 1, "relevance_score": 0.9}]},
    {"object": "list", "model": "m",
     "results": [{"index": 1, "relevance_score": 0.9, "document": {"text": "B"}},
                 {"index": 0, "relevance_score": 0.2}]},
])
def test_accepted_replies(payload):
    assert parse_rerank(payload, 2) == {0: 0.2, 1: 0.9}


def test_a_reply_may_score_only_some_documents_and_scores_may_be_negative():
    assert parse_rerank({"results": [{"index": 1, "relevance_score": -3.5}]}, 2) == {1: -3.5}


@pytest.mark.parametrize("payload, fragment", [
    ([{"index": 0, "relevance_score": 1}], "JSON object"),
    ({"error": {"message": f"bad key {KEY}"}, "request_id": "r1"}, "error, request_id"),
    ({"results": "nope"}, "not a list"),
    ({"results": []}, "none of the 2"),
    ({"data": []}, "none of the 2"),
    ({"results": [{"index": 0}]}, "relevance_score"),
    ({"results": [{"relevance_score": 1}]}, '"index"'),
    ({"results": [{"index": True, "relevance_score": 1}]}, '"index"'),
    ({"results": [{"index": "0", "relevance_score": 1}]}, '"index"'),
    ({"results": [{"index": 2, "relevance_score": 1}]}, "out of range"),
    ({"results": [{"index": -1, "relevance_score": 1}]}, "out of range"),
    ({"results": [{"index": 0, "relevance_score": "0.9"}]}, "relevance_score"),
    ({"results": [{"index": 0, "relevance_score": float("nan")}]}, "relevance_score"),
    ({"results": [{"index": 0, "relevance_score": 1}, {"index": 0, "relevance_score": 2}]}, "twice"),
])
def test_rejected_replies_name_the_problem_and_never_the_content(payload, fragment):
    with pytest.raises(RerankEndpointError) as exc:
        parse_rerank(payload, 2)
    message = str(exc.value)
    assert fragment in message and KEY not in message and "\n" not in message


def test_the_request(embedding_endpoint):
    seen = embedding_endpoint(_reply({"results": [{"index": 1, "relevance_score": 0.9}]}))
    assert _score() == {1: 0.9}
    (request,) = seen.requests
    assert request.method == "POST" and str(request.url) == f"{GATEWAY}/rerank"
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert json.loads(request.content) == {"query": "q", "documents": DOCS}   # no "model"
    assert seen.client_kwargs == [{"timeout": httpx.Timeout(60.0, connect=10.0)}]


def test_the_model_is_sent_only_when_set(embedding_endpoint):
    seen = embedding_endpoint(_reply(ONE))
    _score(model="my-rerank-model")
    assert json.loads(seen.requests[0].content)["model"] == "my-rerank-model"


def test_the_path_goes_before_a_query_in_base_url(embedding_endpoint):
    seen = embedding_endpoint(_reply(ONE))
    _score(base_url=f"{GATEWAY}/?api-version=1")
    assert str(seen.requests[0].url) == f"{GATEWAY}/rerank?api-version=1"


def _refused(request):
    raise httpx.ConnectError("[Errno 61] Connection refused", request=request)


@pytest.mark.parametrize("handler, fragment", [
    (lambda r: httpx.Response(422, json={"detail": f"model field not allowed, key {KEY}"}),
     "returned HTTP 422 Unprocessable Entity"),
    (lambda r: httpx.Response(200, text="<html>sign in</html>"), "not JSON"),
    (_refused, "unreachable (ConnectError: [Errno 61] Connection refused)"),
])
def test_failures_are_one_line_and_show_neither_the_key_nor_the_body(embedding_endpoint, handler, fragment):
    embedding_endpoint(handler)
    with pytest.raises(RerankEndpointError) as exc:
        _score(base_url="https://user:pw@llm.example.com/v1?token=t")
    message = str(exc.value)
    assert message.startswith("rerank endpoint ") and fragment in message
    assert message.endswith(": POST https://llm.example.com/v1/rerank")
    for leaked in (KEY, "user:pw", "token=t", "model field not allowed", "sign in"):
        assert leaked not in message
    assert "\n" not in message


@pytest.mark.parametrize("value", ["", "   ", "k-tést-123", "k-1\r\nX-Evil: 1"])
def test_an_unset_or_unsendable_key_is_refused_before_any_request(embedding_endpoint, monkeypatch, value):
    seen = embedding_endpoint(_reply(ONE))
    monkeypatch.setenv("MY_RERANK_KEY", value)
    with pytest.raises(RerankEndpointError) as exc:
        _score()
    assert "MY_RERANK_KEY" in str(exc.value) and seen.requests == []
    assert "X-Evil" not in str(exc.value) and "tést" not in str(exc.value)
