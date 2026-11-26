"""The `http` embedding type: the request it sends, the replies it accepts, how it fails.

No socket is opened. `embedding_endpoint` (conftest) answers the function's
httpx client in-process.
"""
import json

import httpx
import pytest
from chromadb.utils.embedding_functions import known_embedding_functions

from cortex_vec.http_embedding import (
    NAME,
    EmbeddingEndpointError,
    HttpEmbeddingFunction,
    parse_embeddings,
)

GATEWAY = "https://llm.example.com/v1"
VECS = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
KEY = "k-test-123"


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("MY_EMBED_KEY", KEY)


def _ef(base_url=GATEWAY):
    return HttpEmbeddingFunction(model="my-embedding-model", base_url=base_url,
                                 api_key_env="MY_EMBED_KEY")


def test_the_registered_name_is_cortex_http():
    # Indexes record this name. Renaming it makes every `http` user rebuild.
    assert NAME == HttpEmbeddingFunction.name() == "cortex-http"
    assert known_embedding_functions["cortex-http"] is HttpEmbeddingFunction


@pytest.mark.parametrize("payload", [
    {"object": "list", "model": "m",
     "data": [{"embedding": VECS[1], "index": 1}, {"embedding": VECS[0], "index": 0}]},
    {"data": [{"embedding": VECS[0]}, {"embedding": VECS[1]}]},       # no index: reply order
    {"embedding": VECS},
    {"embeddings": VECS},
])
def test_accepted_replies(payload):
    assert parse_embeddings(payload, 2) == VECS


@pytest.mark.parametrize("payload, fragment", [
    ({"error": {"message": f"bad key {KEY}"}, "request_id": "r1"}, "error, request_id"),
    ([VECS[0]], "JSON object"),
    ({"embedding": VECS}, "2 embeddings for 1 input"),
    ({"embedding": VECS[0]}, "list of numbers"),                      # one flat vector
    ({"embeddings": [["a", "b"]]}, "list of numbers"),
    ({"embedding": [[]]}, "list of numbers"),
    ({"data": [{"index": 0}]}, '"embedding"'),
    ({"data": "nope"}, "not a list"),
])
def test_rejected_replies_name_the_problem_and_never_the_content(payload, fragment):
    with pytest.raises(EmbeddingEndpointError) as exc:
        parse_embeddings(payload, 1)
    message = str(exc.value)
    assert fragment in message and KEY not in message and "\n" not in message


def test_field_names_in_the_message_are_bounded():
    payload = {f"field-{i:02d}-" + "x" * 100: 1 for i in range(50)}
    with pytest.raises(EmbeddingEndpointError) as exc:
        parse_embeddings(payload, 1)
    assert len(str(exc.value)) < 500 and "field-00-" in str(exc.value)


def test_field_names_cannot_break_the_message_into_lines():
    with pytest.raises(EmbeddingEndpointError) as exc:
        parse_embeddings({"first\nsecond\tthird": 1}, 1)
    assert "\n" not in str(exc.value) and "first second third" in str(exc.value)


def test_the_request_is_a_bearer_post_of_model_and_input(embedding_endpoint):
    seen = embedding_endpoint()
    ef = _ef(GATEWAY + "/")                                  # a trailing slash is fine
    assert [v.tolist() for v in ef(["one", "two"])] == [pytest.approx([0.1, 0.2, 0.3])] * 2
    request = seen.requests[0]
    assert (request.method, str(request.url)) == ("POST", GATEWAY + "/embeddings")
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(request.content) == {"model": "my-embedding-model", "input": ["one", "two"]}
    ef(["three"])                                            # the same client is reused
    # Ten seconds to connect: `search` asks twice before it falls back to BM25,
    # and an endpoint that is not there must not hold it for minutes.
    assert seen.client_kwargs == [{"timeout": httpx.Timeout(60.0, connect=10.0)}]


@pytest.mark.parametrize("base_url, sent", [
    (GATEWAY + "?x=1", GATEWAY + "/embeddings?x=1"),
    (GATEWAY + "/?x=1", GATEWAY + "/embeddings?x=1"),
    (GATEWAY + "#part", GATEWAY + "/embeddings"),             # a fragment is never sent
])
def test_embeddings_goes_on_the_path_and_the_query_is_kept(embedding_endpoint, base_url, sent):
    seen = embedding_endpoint()
    _ef(base_url)(["one"])
    assert str(seen.requests[0].url) == sent


def test_the_query_is_sent_but_never_shown(embedding_endpoint):
    # Some gateways take the key in the query string.
    seen = embedding_endpoint(lambda r: httpx.Response(503))
    with pytest.raises(EmbeddingEndpointError) as exc:
        _ef(GATEWAY + "?code=s3cret")(["one"])
    message = str(exc.value)
    assert "POST https://llm.example.com/v1/embeddings" in message and "s3cret" not in message
    assert seen.requests[0].url.params["code"] == "s3cret"


def _refuse(request):
    raise httpx.ConnectError("[Errno 61] Connection refused", request=request)


def _illegal_header(request):
    # What the HTTP layer raises for a header value it refuses: the whole header.
    raise httpx.LocalProtocolError(f"Illegal header value b'Bearer {KEY}'", request=request)


def _garbled_reply(request):
    raise httpx.RemoteProtocolError(
        f"illegal status line: bytearray(b'<html>rejected {KEY}')", request=request)


@pytest.mark.parametrize("handler, fragment", [
    (lambda r: httpx.Response(503, text=f"<html>\nupstream rejected {KEY}\n</html>"), "HTTP 503"),
    (lambda r: httpx.Response(401, json={"error": f"Incorrect API key: {KEY}"}), "HTTP 401"),
    (lambda r: httpx.Response(302, headers={"location": "https://login.example.com/"}), "HTTP 302"),
    # the status line is the endpoint's text too
    (lambda r: httpx.Response(401, extensions={"reason_phrase": f"bad key {KEY}".encode()}), "HTTP 401"),
    (lambda r: httpx.Response(200, text="<html>Sign in to continue</html>"), "not JSON"),
    # the operating system's own text for a failed connection is kept
    (_refuse, "ConnectError: [Errno 61] Connection refused"),
    # any other transport error may quote the request or the reply: type only
    (_illegal_header, "(LocalProtocolError)"),
    (_garbled_reply, "(RemoteProtocolError)"),
])
def test_endpoint_failures_are_one_line_naming_the_url_and_never_a_secret(
        embedding_endpoint, handler, fragment):
    seen = embedding_endpoint(handler)
    with pytest.raises(EmbeddingEndpointError) as exc:
        _ef("https://user:s3cret@llm.example.com/v1")(["one"])
    message = str(exc.value)
    assert fragment in message and "POST https://llm.example.com/v1/embeddings" in message
    assert KEY not in message and "s3cret" not in message and "\n" not in message
    assert len(seen.requests) == 1                           # no retry, no redirect followed


def test_a_missing_key_or_endpoint_is_reported_before_any_request(embedding_endpoint, monkeypatch):
    seen = embedding_endpoint()
    restored = HttpEmbeddingFunction.build_from_config({"model": "my-embedding-model"})
    with pytest.raises(EmbeddingEndpointError, match="models.embedding"):
        restored(["one"])                    # what chroma rebuilds from the index has no endpoint
    monkeypatch.delenv("MY_EMBED_KEY")
    with pytest.raises(EmbeddingEndpointError, match="MY_EMBED_KEY not set"):
        _ef()(["one"])
    assert seen.requests == []


@pytest.mark.parametrize("value", [KEY + "\r", KEY + "\n", f" {KEY} "])
def test_whitespace_around_the_key_is_not_sent(embedding_endpoint, monkeypatch, value):
    # A key saved with a line ending is common. Sent as it is, the HTTP layer
    # refuses the header with an error that quotes all of it.
    monkeypatch.setenv("MY_EMBED_KEY", value)
    seen = embedding_endpoint()
    _ef()(["one"])
    assert seen.requests[0].headers["authorization"] == f"Bearer {KEY}"


@pytest.mark.parametrize("value", ["k-test\r\nX-Injected: 1", "k-tést-123"])
def test_a_key_that_cannot_be_a_header_is_refused_without_being_shown(
        embedding_endpoint, monkeypatch, value):
    monkeypatch.setenv("MY_EMBED_KEY", value)
    seen = embedding_endpoint()
    with pytest.raises(EmbeddingEndpointError) as exc:
        _ef()(["one"])
    message = str(exc.value)
    assert "MY_EMBED_KEY" in message and "k-t" not in message and "\n" not in message
    assert seen.requests == []


def test_a_url_that_does_not_parse_shows_nothing_from_it(embedding_endpoint):
    seen = embedding_endpoint()
    with pytest.raises(EmbeddingEndpointError) as exc:
        _ef("https://user:s3cret/x@llm.example.com/v1")(["one"])     # a password holding "/"
    message = str(exc.value)
    assert "InvalidURL" in message and "s3cret" not in message and "\n" not in message
    assert seen.requests == []


def test_only_the_model_is_persisted():
    ef = _ef("https://user:s3cret@llm.example.com/v1")
    assert ef.get_config() == {"model": "my-embedding-model"}
    assert ef.default_space() == "cosine"
    # chroma calls build_from_config while creating a collection. If that
    # raises, the index is silently recorded as "legacy", with no name at all.
    assert ef.is_legacy() is False
    assert HttpEmbeddingFunction.build_from_config({}).get_config() == {"model": ""}
