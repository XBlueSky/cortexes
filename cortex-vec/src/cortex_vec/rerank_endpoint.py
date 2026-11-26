"""The `endpoint` rerank type: scores documents through `POST {base_url}/rerank`.

The request is `{"query": ..., "documents": [...]}` with a bearer key, plus
`"model"` only when one is set: some endpoints refuse the field. The reply
shapes are listed at `parse_rerank`.

Only `http_endpoint` is imported here, never `http_embedding`, which loads
chromadb.
"""
import math

from .http_endpoint import EndpointError, endpoint_url, field_names, is_number, new_client, post_json, read_key

_REPLY_KEYS = ("results", "data")


class RerankEndpointError(EndpointError):
    """The rerank endpoint could not be used, or its reply could not be read."""


def parse_rerank(payload, count):
    """Return {document position: score} from a decoded reply, or raise.

    Accepted replies, with any other fields on the reply or its items:
      {"results": [{"index": n, "relevance_score": s}, ...]}
      {"data": [{"index": n, "relevance_score": s}, ...]}

    The reply may score only some of the `count` documents (an endpoint with
    a default top_n does that), but not none of them. Any item that is not
    usable fails the whole reply: a half-read order is worse than the
    original one.
    """
    if not isinstance(payload, dict):
        raise RerankEndpointError("rerank response is not a JSON object")
    key = next((k for k in _REPLY_KEYS if k in payload), None)
    if key is None:
        raise RerankEndpointError(
            'rerank response has neither "results" nor "data" '
            f"(top-level fields: {field_names(payload)})")
    items = payload[key]
    if not isinstance(items, list):
        raise RerankEndpointError(f'"{key}" in the rerank response is not a list')
    scores = {}
    for i, item in enumerate(items):
        where = f"{key}[{i}] in the rerank response"
        if not isinstance(item, dict):
            raise RerankEndpointError(f"{where} is not an object")
        index = item.get("index")
        if type(index) is not int:                      # a bool is not an index
            raise RerankEndpointError(f'{where} has no integer "index"')
        if not 0 <= index < count:
            # The value is not shown: a huge one would not fit on a line.
            raise RerankEndpointError(f'{where} has an "index" out of range for {count} documents')
        if index in scores:
            raise RerankEndpointError(f"index {index} appears twice in the rerank response")
        scores[index] = _score_of(item.get("relevance_score"), where)
    if count and not scores:
        raise RerankEndpointError(f"rerank response scored none of the {count} documents")
    return scores


def _score_of(value, where):
    number = None
    if is_number(value):
        try:
            number = float(value)
        except OverflowError:                           # an int too large for a float
            pass
    if number is None or not math.isfinite(number):
        raise RerankEndpointError(f'{where} has no finite number "relevance_score"')
    return number


def score(query, documents, *, model, base_url, api_key_env):
    """Score `documents` against `query`; return {document position: score}.

    Raises RerankEndpointError, with a one-line message, for anything that
    keeps the endpoint from answering usefully.
    """
    key = read_key(api_key_env, RerankEndpointError)
    url = endpoint_url(base_url, "rerank")
    body = {"query": query, "documents": list(documents)}
    if model:
        body["model"] = model
    with new_client() as client:
        payload = post_json(client, url, key, body, "rerank endpoint", RerankEndpointError)
    return parse_rerank(payload, len(documents))
