"""Model clients, built from the `models` block of ~/.cortex/config.json.

This is the only module that constructs an embedding function or a chat
client. A new provider type is added here and in `config._MODEL_TYPES`, and
nowhere else.

chromadb and openai are imported inside the functions, not at module level:
store.py has to swap in pysqlite3 before chromadb is first imported, and this
module must not get there first.
"""

import os

from . import config
from .errors import EXIT_SETUP, CliError

_DEFAULT_KEY_ENV = "OPENAI_API_KEY"
_LABELS = {"openai": "OpenAI", "azure": "Azure OpenAI"}


def _role(role):
    return config.get_models_config()[role]


# ── embedding ────────────────────────────────────────────────────────────────

def embedding_key_env():
    """Name of the env var that holds the embedding key."""
    return _role("embedding")["api_key_env"]


def embedding_available():
    """True when the embedding key is set, i.e. the vector stream can run."""
    return bool(os.environ.get(embedding_key_env()))


def embedding_function():
    """Return the chroma embedding function for `models.embedding`."""
    import chromadb.utils.embedding_functions as chroma_ef

    mc = _role("embedding")
    key_env = mc["api_key_env"]
    api_key = os.environ.get(key_env, "")
    if not api_key:
        raise CliError(
            f"{key_env} not set",
            "export it for embeddings; `cortex-vec rebuild --bm25-only` "
            "works without it",
            code=EXIT_SETUP)
    # The key is always passed explicitly: left to itself chroma reads
    # OPENAI_API_KEY whenever that is set, whatever variable it was told to use.
    kwargs = {"model_name": mc["model"], "api_key": api_key}
    if mc["base_url"]:
        kwargs["api_base"] = mc["base_url"]
    if key_env != _DEFAULT_KEY_ENV:
        # chroma stores the variable's name (never the key) with the collection
        kwargs["api_key_env_var"] = key_env
    return chroma_ef.OpenAIEmbeddingFunction(**kwargs)


def embedding_signature():
    """What an index must have been built with to be searchable now.

    The endpoint is left out on purpose: the same model behind another URL
    yields the same vectors.
    """
    mc = _role("embedding")
    return {"type": mc["type"], "model": mc["model"]}


# ── chat ─────────────────────────────────────────────────────────────────────

def _chat_key(key_env):
    key = os.environ.get(key_env, "")
    if not key:
        raise CliError(
            f"{key_env} not set",
            f"export it, or change models.chat.api_key_env in {config.CORTEX_CONFIG}",
            code=EXIT_SETUP)
    return key


def chat_client():
    """Return the chat client for `models.chat` (summaries, rerank, eval)."""
    import openai

    mc = _role("chat")
    key_env = mc["api_key_env"]
    if mc["type"] == "azure":
        return openai.AzureOpenAI(azure_endpoint=mc["base_url"],
                                  api_version=mc["api_version"],
                                  api_key=_chat_key(key_env))
    # Pass only what is configured: with nothing set this is `OpenAI()`, and the
    # SDK keeps reading OPENAI_API_KEY and OPENAI_BASE_URL on its own.
    kwargs = {}
    if mc["base_url"]:
        kwargs["base_url"] = mc["base_url"]
    if key_env != _DEFAULT_KEY_ENV:
        kwargs["api_key"] = _chat_key(key_env)
    return openai.OpenAI(**kwargs)


def chat_model():
    """Model name (for Azure: the deployment name) to pass to the chat client."""
    return _role("chat")["model"]


# ── reporting ────────────────────────────────────────────────────────────────

def describe(role):
    """Return {"model", "type", "label"} for `role` ("embedding" or "chat")."""
    mc = _role(role)
    return {"model": mc["model"], "type": mc["type"], "label": _LABELS[mc["type"]]}
