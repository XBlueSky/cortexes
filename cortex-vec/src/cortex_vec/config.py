"""Configuration loading and constants."""

import json
from pathlib import Path

from .errors import EXIT_SETUP, CliError

CORTEX_CONFIG = Path.home() / ".cortex" / "config.json"
VECTORSTORE_DIR = Path.home() / ".cortex" / "vectorstore"
COLLECTION_NAME = "cortex"
SUMMARY_MODEL = "gpt-5.4-mini"
BM25_DIR = Path.home() / ".cortex" / "bm25"

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
    "rerank_model": "gpt-5.4-mini",
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
