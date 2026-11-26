"""The `http` embedding type: a chroma embedding function for a plain HTTP endpoint.

It sends `POST {base_url}/embeddings` with a bearer key and reads the reply
shapes listed at `parse_embeddings`, for endpoints that take an OpenAI-style
request but do not answer in the OpenAI shape.

chromadb is imported at the top of this module, so load it only after
`store.py` has swapped in pysqlite3: from `store.py` itself, or with an import
inside a function, as `providers.py` does.
"""
import os

import httpx
from chromadb.api.types import Documents, EmbeddingFunction
from chromadb.utils.embedding_functions import register_embedding_function

from .errors import brief

# Every index built through this type records this name, and chroma refuses to
# open it under another one. Renaming it makes every `http` user rebuild.
NAME = "cortex-http"
# Ten seconds to connect and sixty for the reply. `search` asks twice before
# it falls back to BM25, so an endpoint that is not there must give up fast.
TIMEOUT_SECONDS = 60.0
CONNECT_TIMEOUT_SECONDS = 10.0

_REPLY_KEYS = ("data", "embedding", "embeddings")
_MAX_FIELDS = 8
_MAX_FIELD_CHARS = 40

# The transport errors whose own text goes into a message: it comes from the
# operating system or the TLS library. Any other one may quote the request
# (the HTTP layer names the whole Authorization header when it refuses its
# value), the URL, or bytes the endpoint sent, so only its type is shown.
_DESCRIBED = (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError, httpx.WriteError)


class EmbeddingEndpointError(RuntimeError):
    """The endpoint could not be used, or its reply could not be read.

    Built from one single-line string and nothing else: chroma rewrites
    `args[0]` in place ("... in upsert.") before it re-raises. The message
    never holds the key, the URL's userinfo or query, or a reply body, since
    an endpoint may echo the key back in an error. What it can hold from
    outside this program: the reply's top-level field names, bounded, and the
    text of a `_DESCRIBED` error.
    """


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _field_names(payload):
    """The reply's top-level field names, bounded and on one line."""
    names = [" ".join(str(name).split())[:_MAX_FIELD_CHARS] for name in list(payload)[:_MAX_FIELDS]]
    if not names:
        return "none"
    return ", ".join(names) + (", …" if len(payload) > _MAX_FIELDS else "")


def parse_embeddings(payload, expected):
    """Return one vector per input from a decoded reply, or raise.

    Accepted replies:
      {"data": [{"embedding": [...], "index": n}, ...]}   (the OpenAI shape)
      {"embedding": [[...], ...]}
      {"embeddings": [[...], ...]}

    chroma takes a flat list of numbers as a single vector without complaint,
    so the shape is checked here, and before the count: a flat vector is then
    reported as what it is.
    """
    if not isinstance(payload, dict):
        raise EmbeddingEndpointError("embedding response is not a JSON object")
    key = next((k for k in _REPLY_KEYS if k in payload), None)
    if key is None:
        raise EmbeddingEndpointError(
            'embedding response has none of "data", "embedding", "embeddings" '
            f"(top-level fields: {_field_names(payload)})")
    vectors = payload[key]
    if not isinstance(vectors, list):
        raise EmbeddingEndpointError(f'"{key}" in the embedding response is not a list')
    if key == "data":
        for i, item in enumerate(vectors):
            if not isinstance(item, dict) or "embedding" not in item:
                raise EmbeddingEndpointError(
                    f'data[{i}] in the embedding response has no "embedding"')
        if all(type(item.get("index")) is int for item in vectors):
            vectors = sorted(vectors, key=lambda item: item["index"])
        vectors = [item["embedding"] for item in vectors]
    for i, vector in enumerate(vectors):
        if not (isinstance(vector, list) and vector and all(_is_number(x) for x in vector)):
            raise EmbeddingEndpointError(
                f"embedding {i} in the response is not a non-empty list of numbers")
    if len(vectors) != expected:
        raise EmbeddingEndpointError(
            f"embedding endpoint returned {len(vectors)} embeddings for {expected} inputs")
    return vectors


def _embeddings_url(base_url):
    """`{base_url}/embeddings`, with any query kept after the new path.

    The fragment is dropped, since it is never sent. Plain string work, so the
    URL's own percent-encoding reaches the request unchanged.
    """
    path, sep, query = base_url.partition("#")[0].partition("?")
    return f"{path.rstrip('/')}/embeddings{sep}{query}"


def _request_line(url):
    """`: POST <url>` for a message, without userinfo or query: either may hold a credential."""
    try:
        return f": POST {httpx.URL(url).copy_with(userinfo=b'', query=None)}"
    except Exception:
        return ""


@register_embedding_function
class HttpEmbeddingFunction(EmbeddingFunction[Documents]):
    """Embeds through `POST {base_url}/embeddings`.

    The key is read from the environment on each call and is never kept on the
    instance. Only the model is persisted with the index (see `get_config`).
    """

    def __init__(self, model, base_url=None, api_key_env="OPENAI_API_KEY"):
        self._model = model
        self._base_url = base_url
        self._api_key_env = api_key_env
        self._client = None

    def __call__(self, input):
        if not self._base_url:
            raise EmbeddingEndpointError(
                f"{NAME} has no endpoint here; cortex-vec supplies it from models.embedding")
        # Stripped: a key saved with a line ending is common. Anything else
        # that cannot go into a header is refused here, because the HTTP
        # layer would refuse it with an error that quotes the key.
        key = os.environ.get(self._api_key_env, "").strip()
        if not key:
            raise EmbeddingEndpointError(f"{self._api_key_env} not set")
        if not (key.isascii() and key.isprintable()):
            raise EmbeddingEndpointError(
                f"{self._api_key_env} holds a character that cannot be sent in an HTTP header")
        url = _embeddings_url(self._base_url)
        request_line = _request_line(url)
        if self._client is None:
            # No transport argument: httpx then honours the proxy and CA
            # environment variables. One attempt, and redirects are not
            # followed, so the key is never sent on to another host.
            self._client = httpx.Client(
                timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS))
        try:
            response = self._client.post(
                url, headers={"Authorization": f"Bearer {key}"},
                json={"model": self._model, "input": list(input)})
        except (httpx.HTTPError, httpx.InvalidURL) as e:
            reason = brief(e) if isinstance(e, _DESCRIBED) else type(e).__name__
            raise EmbeddingEndpointError(
                f"embedding endpoint unreachable ({reason}){request_line}") from None
        if not response.is_success:
            # The standard phrase for the code, not the one on the status line.
            status = f"{response.status_code} {httpx.codes.get_reason_phrase(response.status_code)}"
            raise EmbeddingEndpointError(
                f"embedding endpoint returned HTTP {status.strip()}{request_line}")
        try:
            payload = response.json()
        except ValueError:
            raise EmbeddingEndpointError(
                f"embedding endpoint returned HTTP {response.status_code} "
                f"but the body is not JSON{request_line}") from None
        return parse_embeddings(payload, len(input))

    @staticmethod
    def name():
        return NAME

    def default_space(self):
        return "cosine"

    @staticmethod
    def build_from_config(config):
        # chroma calls this while it creates a collection. If it raises, the
        # index is recorded as "legacy": no name, and no conflict check later.
        # So this needs no key and no endpoint, and must not raise.
        return HttpEmbeddingFunction(model=config.get("model", ""))

    def get_config(self):
        # The model only. The endpoint can change without touching the index,
        # and chroma echoes this dict in its own error messages.
        return {"model": self._model}
