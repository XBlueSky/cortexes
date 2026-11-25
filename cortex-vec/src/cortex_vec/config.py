"""Configuration loading and constants."""

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from .errors import EXIT_SETUP, CliError

CORTEX_CONFIG = Path.home() / ".cortex" / "config.json"
VECTORSTORE_DIR = Path.home() / ".cortex" / "vectorstore"
COLLECTION_NAME = "cortex"
EMBEDDING_MODEL = "text-embedding-3-small"
SUMMARY_MODEL = "gpt-5.4-mini"
BM25_DIR = Path.home() / ".cortex" / "bm25"

# The `models` block: one entry per role, each merged over these defaults.
_MODELS_DEFAULTS = {
    "embedding": {"type": "openai", "model": EMBEDDING_MODEL, "base_url": None,
                  "api_key_env": "OPENAI_API_KEY"},
    "chat": {"type": "openai", "model": SUMMARY_MODEL, "base_url": None,
             "api_key_env": "OPENAI_API_KEY", "api_version": None},
}

# role -> type -> (fields that type accepts, fields it requires)
_MODEL_TYPES = {
    "embedding": {
        "openai": (("model", "base_url", "api_key_env"), ()),
        "http": (("model", "base_url", "api_key_env"), ()),
    },
    "chat": {
        "openai": (("model", "base_url", "api_key_env"), ()),
        "azure": (("model", "base_url", "api_key_env", "api_version"),
                  ("base_url", "api_version")),
    },
}

# (role, type) -> env var that supplies `base_url` when the block leaves it
# out. These types call the endpoint themselves, so they need a usable URL
# before the command starts.
_BASE_URL_ENV = {("embedding", "http"): "OPENAI_BASE_URL"}

_RETRIEVAL_DEFAULTS = {
    # Plan 1
    "rrf_k": 60,
    "w_bm25": 0.4,
    "w_vec": 0.6,
    "max_per_repo": 0,
    # Plan 2
    "synonym_weight": 0.0,      # 0 = synonym expansion off
    "graph": False,
    "graph_hops": 1,
    "w_graph": 0.3,             # graph stream weight in RRF (rank-based, not additive)
    "graph_top_k": 5,           # how many top hits to expand wikilink-neighbors from
    "rerank": False,
    "rerank_model": None,       # unset = follow models.chat.model
    "rerank_window": 15,
}


def load_config():
    """Load ~/.cortex/config.json; raise CliError if it is missing."""
    if not CORTEX_CONFIG.exists():
        raise CliError(f"{CORTEX_CONFIG} not found", "run /cortexes:genesis first",
                       code=EXIT_SETUP)
    with open(CORTEX_CONFIG) as f:
        return json.load(f)


def get_vault_path():
    """Return the vault path from config; raise CliError if it is invalid."""
    cfg = load_config()
    vault = cfg.get("vault_path", "")
    if not vault or not Path(vault).is_dir():
        raise CliError(f"vault_path '{vault}' is not a directory",
                       f"fix vault_path in {CORTEX_CONFIG} or rerun /cortexes:genesis",
                       code=EXIT_SETUP)
    return Path(vault)


def get_retrieval_config():
    """Return retrieval settings merged over defaults."""
    cfg = load_config()
    rc = dict(_RETRIEVAL_DEFAULTS)
    rc.update(cfg.get("retrieval", {}))
    return rc


# Uppercase only. Plain letters and digits would also let through a key that
# has no prefix or punctuation (a hex key, say), and the name is printed later.
_ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")


def _bad_models(path, problem, hint=""):
    return CliError(f"invalid {path} in {CORTEX_CONFIG}: {problem}", hint, code=EXIT_SETUP)


def _is_http_url(url):
    """True for an http:// or https:// URL with a host that a request can use."""
    # Checked before parsing: urlsplit silently drops tabs and line endings.
    if any(c.isspace() or not c.isprintable() for c in url):
        return False
    try:
        parts = urlsplit(url)
        parts.port                          # raises for a port that is not a number
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.hostname)


def get_models_config():
    """Return the `models` block merged over defaults, one dict per role.

    Raises CliError (exit 3) on the first thing wrong with the block. Messages
    name the field and what it accepts but do not echo a field's value: the
    likeliest mistake is a key pasted where an env var name belongs. The one
    exception is an unknown `type`, which is shown; it is a word picked from
    a short list, not a place a key ends up.

    For the types listed in `_BASE_URL_ENV` the returned `base_url` is final:
    the block's value, or else the env var's. For the others it stays None
    when the block does not set it, and the SDK reads its own env var.
    """
    models = load_config().get("models")
    if models is None:                      # null = unset, at every level
        models = {}
    if not isinstance(models, dict):
        raise _bad_models("models", "must be an object")
    for role in models:
        if role not in _MODELS_DEFAULTS:
            raise _bad_models(f"models.{role}", "unknown role",
                              "valid roles: " + ", ".join(_MODELS_DEFAULTS))
    return {role: _merge_role(role, models.get(role)) for role in _MODELS_DEFAULTS}


def _merge_role(role, user):
    path = f"models.{role}"
    defaults = _MODELS_DEFAULTS[role]
    if user is None:
        user = {}
    if not isinstance(user, dict):
        raise _bad_models(path, "must be an object")
    for field in user:
        if field not in defaults:
            raise _bad_models(f"{path}.{field}", "unknown field",
                              "valid fields: " + ", ".join(defaults))
    for field, value in user.items():
        if value is not None and not (isinstance(value, str) and value):
            raise _bad_models(f"{path}.{field}", "must be a non-empty string")
    # Later messages print this name ("<name> not set"), so it has to look
    # like one: a pasted key must stop here, where its value is not shown.
    key_env = user.get("api_key_env")
    if key_env is not None and not _ENV_NAME.fullmatch(key_env):
        raise _bad_models(f"{path}.api_key_env",
                          "must be the name of an environment variable, not the key itself",
                          "uppercase letters, digits and underscores only, "
                          "e.g. OPENAI_API_KEY")

    merged = dict(defaults)
    merged.update({k: v for k, v in user.items() if v is not None})   # null = unset

    types = _MODEL_TYPES[role]
    kind = merged["type"]
    if kind not in types:
        raise _bad_models(f"{path}.type", f"unknown type {kind!r}",
                          "valid values: " + ", ".join(types))
    settable, required = types[kind]
    for field, value in user.items():
        if field != "type" and value is not None and field not in settable:
            raise _bad_models(f"{path}.{field}", f"does not apply to type '{kind}'",
                              f"fields for '{kind}': " + ", ".join(settable))
    for field in required:
        if merged[field] is None:
            raise _bad_models(f"{path}.{field}", f"required when type is '{kind}'")

    # Settled here, not when the first request is made: `rebuild` deletes the
    # collection before it embeds anything.
    env = _BASE_URL_ENV.get((role, kind))
    if env:
        url = merged["base_url"] or os.environ.get(env)     # an empty variable is unset
        if not url:
            raise _bad_models(f"{path}.base_url", f"required when type is '{kind}'",
                              f"set it, or export {env}")
        if not _is_http_url(url):
            raise _bad_models(f"{path}.base_url", "must be an http:// or https:// URL with a host",
                              f"when the field is not set, the value comes from {env}")
        merged["base_url"] = url
    return merged


def get_view_config():
    """Return raw-view settings merged over defaults. Tolerates missing config."""
    from .raw_view import VIEW_DEFAULTS
    vc = dict(VIEW_DEFAULTS)
    if CORTEX_CONFIG.exists():
        with open(CORTEX_CONFIG) as f:
            cfg = json.load(f)
        vc.update(cfg.get("distill", {}).get("view", {}))
    return vc


_MAP_DEFAULTS = {"page_budget": 12000, "session_budget": 100000}


def get_map_config():
    """Return map-first page/session budgets merged over defaults."""
    mc = dict(_MAP_DEFAULTS)
    if CORTEX_CONFIG.exists():
        with open(CORTEX_CONFIG) as f:
            cfg = json.load(f)
        mc.update(cfg.get("distill", {}).get("map", {}))
    return mc
