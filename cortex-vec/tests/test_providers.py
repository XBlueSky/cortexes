"""providers: the one place that turns the `models` block into model clients."""
import json

import chromadb.utils.embedding_functions as chroma_ef
import openai
import pytest

from cortex_vec import config, http_embedding, providers
from cortex_vec.errors import EXIT_SETUP, CliError

GATEWAY = "https://llm.example.com/v1"


class _Rec:
    """Stands in for a client class and records how it was constructed."""

    def __init__(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs


def _cfg(monkeypatch, models):
    monkeypatch.setattr(config, "load_config", lambda: {"models": models})


def test_default_embedding_function_is_built_exactly_as_before(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(chroma_ef, "OpenAIEmbeddingFunction", _Rec)
    ef = providers.embedding_function()
    assert ef.args == ()
    assert ef.kwargs == {"model_name": "text-embedding-3-small", "api_key": "test-key"}


def test_embedding_openai_passes_model_base_url_and_key_env(monkeypatch):
    _cfg(monkeypatch, {"embedding": {"model": "my-embedding-model", "base_url": GATEWAY,
                                     "api_key_env": "MY_EMBED_KEY"}})
    monkeypatch.setenv("MY_EMBED_KEY", "k2")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(chroma_ef, "OpenAIEmbeddingFunction", _Rec)
    assert providers.embedding_function().kwargs == {
        "model_name": "my-embedding-model", "api_key": "k2",
        "api_base": GATEWAY, "api_key_env_var": "MY_EMBED_KEY"}


# chroma warns that a key passed directly is not persisted, which is the point.
@pytest.mark.filterwarnings("ignore:Direct api_key configuration:DeprecationWarning")
def test_configured_embedding_function_constructs_offline_on_the_installed_chroma(monkeypatch):
    _cfg(monkeypatch, {"embedding": {"model": "my-embedding-model", "base_url": GATEWAY,
                                     "api_key_env": "MY_EMBED_KEY"}})
    monkeypatch.setenv("MY_EMBED_KEY", "k2")
    assert type(providers.embedding_function()).__name__ == "OpenAIEmbeddingFunction"


def test_embedding_availability_and_error_follow_api_key_env(monkeypatch):
    _cfg(monkeypatch, {"embedding": {"api_key_env": "MY_EMBED_KEY"}})
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.delenv("MY_EMBED_KEY", raising=False)
    assert providers.embedding_key_env() == "MY_EMBED_KEY"
    assert providers.embedding_available() is False
    with pytest.raises(CliError) as exc:
        providers.embedding_function()
    assert exc.value.code == EXIT_SETUP
    assert "MY_EMBED_KEY not set" in exc.value.render() and "--bm25-only" in exc.value.render()
    monkeypatch.setenv("MY_EMBED_KEY", "k")
    assert providers.embedding_available() is True


def test_default_chat_client_is_openai_with_no_arguments(monkeypatch):
    # No arguments: the SDK keeps reading OPENAI_API_KEY and OPENAI_BASE_URL itself.
    monkeypatch.setattr(openai, "OpenAI", _Rec)
    client = providers.chat_client()
    assert client.args == () and client.kwargs == {}
    assert providers.chat_model() == "gpt-5.4-mini"


def test_chat_openai_passes_only_what_is_configured(monkeypatch):
    monkeypatch.setattr(openai, "OpenAI", _Rec)
    _cfg(monkeypatch, {"chat": {"model": "my-chat-model", "base_url": GATEWAY}})
    assert providers.chat_client().kwargs == {"base_url": GATEWAY}
    _cfg(monkeypatch, {"chat": {"model": "my-chat-model", "base_url": GATEWAY,
                                "api_key_env": "MY_CHAT_KEY"}})
    monkeypatch.setenv("MY_CHAT_KEY", "k3")
    assert providers.chat_client().kwargs == {"base_url": GATEWAY, "api_key": "k3"}
    assert providers.chat_model() == "my-chat-model"


def test_chat_azure(monkeypatch):
    _cfg(monkeypatch, {"chat": {"type": "azure", "model": "my-deployment",
                                "base_url": "https://chat.example.com",
                                "api_version": "2024-06-01", "api_key_env": "MY_CHAT_KEY"}})
    monkeypatch.setenv("MY_CHAT_KEY", "k3")
    monkeypatch.setattr(openai, "AzureOpenAI", _Rec)
    assert providers.chat_client().kwargs == {
        "azure_endpoint": "https://chat.example.com", "api_version": "2024-06-01", "api_key": "k3"}
    assert providers.chat_model() == "my-deployment"


@pytest.mark.parametrize("chat", [
    {"api_key_env": "MY_CHAT_KEY"},
    {"type": "azure", "base_url": "https://chat.example.com", "api_version": "2024-06-01",
     "api_key_env": "MY_CHAT_KEY"},
])
def test_a_named_chat_key_that_is_unset_is_an_error_not_a_fallback(monkeypatch, chat):
    _cfg(monkeypatch, {"chat": chat})
    monkeypatch.setenv("OPENAI_API_KEY", "some-other-key")
    monkeypatch.delenv("MY_CHAT_KEY", raising=False)
    monkeypatch.setattr(openai, "OpenAI", _Rec)
    monkeypatch.setattr(openai, "AzureOpenAI", _Rec)
    with pytest.raises(CliError) as exc:
        providers.chat_client()
    assert "MY_CHAT_KEY not set" in exc.value.render()


def test_describe_and_signature(monkeypatch):
    assert providers.describe("embedding") == {
        "model": "text-embedding-3-small", "type": "openai", "label": "OpenAI"}
    assert providers.describe("chat") == {"model": "gpt-5.4-mini", "type": "openai", "label": "OpenAI"}
    assert providers.embedding_signature() == {"type": "openai", "model": "text-embedding-3-small"}
    _cfg(monkeypatch, {
        "embedding": {"model": "my-embedding-model", "base_url": GATEWAY},
        "chat": {"type": "azure", "model": "my-deployment",
                 "base_url": "https://chat.example.com", "api_version": "2024-06-01"}})
    assert providers.describe("chat")["label"] == "Azure OpenAI"
    assert providers.embedding_signature() == {"type": "openai", "model": "my-embedding-model"}


def test_embedding_http_posts_to_the_configured_endpoint(monkeypatch, embedding_endpoint):
    _cfg(monkeypatch, {"embedding": {"type": "http", "model": "my-embedding-model",
                                     "base_url": GATEWAY, "api_key_env": "MY_EMBED_KEY"}})
    monkeypatch.setenv("MY_EMBED_KEY", "k2")
    monkeypatch.setenv("OPENAI_API_KEY", "some-other-key")
    seen = embedding_endpoint()
    ef = providers.embedding_function()
    assert type(ef) is http_embedding.HttpEmbeddingFunction
    ef(["x"])
    request = seen.requests[0]
    assert str(request.url) == GATEWAY + "/embeddings"
    assert request.headers["authorization"] == "Bearer k2"
    assert json.loads(request.content) == {"model": "my-embedding-model", "input": ["x"]}
    assert providers.embedding_signature() == {"type": "http", "model": "my-embedding-model"}
    assert providers.describe("embedding") == {
        "model": "my-embedding-model", "type": "http", "label": "HTTP endpoint"}


def test_embedding_http_without_its_key_is_the_same_setup_error(monkeypatch):
    _cfg(monkeypatch, {"embedding": {"type": "http", "base_url": GATEWAY,
                                     "api_key_env": "MY_EMBED_KEY"}})
    monkeypatch.setenv("OPENAI_API_KEY", "some-other-key")
    assert providers.embedding_available() is False
    with pytest.raises(CliError) as exc:
        providers.embedding_function()
    assert exc.value.code == EXIT_SETUP and "MY_EMBED_KEY not set" in exc.value.render()


def test_http_follows_OPENAI_BASE_URL_per_command_and_keeps_its_signature(monkeypatch, embedding_endpoint):
    # The block leaves base_url out, so one command can be sent to another gateway.
    _cfg(monkeypatch, {"embedding": {"type": "http", "model": "my-embedding-model"}})
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    seen = embedding_endpoint()
    signatures = []
    for host in ("a", "b"):
        monkeypatch.setenv("OPENAI_BASE_URL", f"https://{host}.example.com/v1")
        providers.embedding_function()(["x"])
        signatures.append(providers.embedding_signature())
    assert [str(r.url) for r in seen.requests] == [
        "https://a.example.com/v1/embeddings", "https://b.example.com/v1/embeddings"]
    assert signatures == [{"type": "http", "model": "my-embedding-model"}] * 2
