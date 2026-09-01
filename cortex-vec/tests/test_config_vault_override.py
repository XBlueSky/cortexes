"""CORTEX_VAULT_PATH overrides vault_path, as both READMEs have always claimed.

The shell hooks honoured the variable from the start; the Python resolver did
not, so the documented override silently did nothing for the CLI and for every
skill that resolves the vault through it.
"""
import json

import pytest

from cortex_vec import config

# conftest's autouse _isolate_retrieval_config stubs load_config to `lambda: {}`.
# These tests are about load_config itself, so grab the real one at import time
# (before any fixture runs) and restore it per test.
_REAL_LOAD_CONFIG = config.load_config


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    """Point CORTEX_CONFIG at a temp file and restore the real loader."""
    path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CORTEX_CONFIG", path)
    monkeypatch.setattr(config, "load_config", _REAL_LOAD_CONFIG)
    monkeypatch.delenv("CORTEX_VAULT_PATH", raising=False)
    return path


def test_env_override_wins_over_config(tmp_path, cfg_file, monkeypatch):
    from_config = tmp_path / "from-config"
    from_env = tmp_path / "from-env"
    from_config.mkdir()
    from_env.mkdir()
    cfg_file.write_text(json.dumps({"vault_path": str(from_config)}))

    monkeypatch.setenv("CORTEX_VAULT_PATH", str(from_env))
    assert config.get_vault_path() == from_env


def test_config_is_used_when_override_absent(tmp_path, cfg_file):
    vault = tmp_path / "vault"
    vault.mkdir()
    cfg_file.write_text(json.dumps({"vault_path": str(vault)}))
    assert config.get_vault_path() == vault


def test_override_makes_the_config_file_optional(tmp_path, cfg_file, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    assert not cfg_file.exists()
    monkeypatch.setenv("CORTEX_VAULT_PATH", str(vault))
    assert config.get_vault_path() == vault
    assert config.load_config() == {}
    # Retrieval settings still resolve, from defaults.
    assert config.get_retrieval_config()["rrf_k"] == 60


def test_missing_config_without_override_still_exits(cfg_file):
    assert not cfg_file.exists()
    with pytest.raises(SystemExit):
        config.get_vault_path()


def test_override_pointing_at_a_non_directory_exits(tmp_path, cfg_file, monkeypatch):
    monkeypatch.setenv("CORTEX_VAULT_PATH", str(tmp_path / "nope"))
    with pytest.raises(SystemExit):
        config.get_vault_path()
