"""Configuration loading and constants."""

import json
import sys
from pathlib import Path

CORTEX_CONFIG = Path.home() / ".cortex" / "config.json"
VECTORSTORE_DIR = Path.home() / ".cortex" / "vectorstore"
COLLECTION_NAME = "cortex"
SUMMARY_MODEL = "gpt-5.4-mini"
BM25_DIR = Path.home() / ".cortex" / "bm25"

_RETRIEVAL_DEFAULTS = {
    "rrf_k": 60,
    "w_bm25": 0.4,
    "w_vec": 0.6,
    "max_per_repo": 0,
}


def load_config():
    """Load ~/.cortex/config.json. Exit with error if not found."""
    if not CORTEX_CONFIG.exists():
        print(
            "Error: ~/.cortex/config.json not found. Run /cortex:genesis first.",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(CORTEX_CONFIG) as f:
        return json.load(f)


def get_vault_path():
    """Return the vault path from config. Exit with error if invalid."""
    cfg = load_config()
    vault = cfg.get("vault_path", "")
    if not vault or not Path(vault).is_dir():
        print(f"Error: vault_path '{vault}' not found.", file=sys.stderr)
        sys.exit(1)
    return Path(vault)


def get_retrieval_config():
    """Return retrieval settings merged over defaults."""
    cfg = load_config()
    rc = dict(_RETRIEVAL_DEFAULTS)
    rc.update(cfg.get("retrieval", {}))
    return rc
