"""The `http` embedding type: a chroma embedding function for a plain HTTP endpoint.

It sends `POST {base_url}/embeddings` with a bearer key and reads the reply
shapes listed at `parse_embeddings`, for endpoints that take an OpenAI-style
request but do not answer in the OpenAI shape.

chromadb is imported at the top of this module, so load it only after
`store.py` has swapped in pysqlite3: from `store.py` itself, or with an import
inside a function, as `providers.py` does.
The request itself (key checks, client, error messages) is in
`http_endpoint.py`, shared with the `endpoint` rerank type.
"""
from chromadb.api.types import Documents, EmbeddingFunction
from chromadb.utils.embedding_functions import register_embedding_function

from .http_endpoint import (
    EndpointError,
    endpoint_url,
    field_names,
    is_number,
    new_client,
    post_json,
    read_key,
)

# Every index built through this type records this name, and chroma refuses to
# open it under another one. Renaming it makes every `http` user rebuild.
NAME = "cortex-http"

_REPLY_KEYS = ("data", "embedding", "embeddings")


class EmbeddingEndpointError(EndpointError):
    """The embedding endpoint could not be used, or its reply could not be read.

    Built from one single-line string and nothing else: chroma rewrites
    `args[0]` in place ("... in upsert.") before it re-raises. What the
    message may hold is described at `EndpointError`.
    """


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
            f"(top-level fields: {field_names(payload)})")
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
        if not (isinstance(vector, list) and vector and all(is_number(x) for x in vector)):
            raise EmbeddingEndpointError(
                f"embedding {i} in the response is not a non-empty list of numbers")
    if len(vectors) != expected:
        raise EmbeddingEndpointError(
            f"embedding endpoint returned {len(vectors)} embeddings for {expected} inputs")
    return vectors


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
        key = read_key(self._api_key_env, EmbeddingEndpointError)
        url = endpoint_url(self._base_url, "embeddings")
        if self._client is None:
            self._client = new_client()
        payload = post_json(self._client, url, key, {"model": self._model, "input": list(input)},
                            "embedding endpoint", EmbeddingEndpointError)
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
