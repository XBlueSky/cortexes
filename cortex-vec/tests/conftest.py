"""Shared pytest fixtures."""
import pytest

from cortex_vec import config


@pytest.fixture(autouse=True)
def _isolate_retrieval_config(monkeypatch):
    """Isolate every test from the developer's real ~/.cortex/config.json.

    `get_retrieval_config()` reads `load_config()`, so without this a local
    `retrieval` override (e.g. rerank=true) would leak into tests and break
    assertions about code defaults. Tests that need a specific config still
    override `config.load_config` themselves (their setattr wins over this).
    """
    monkeypatch.setattr(config, "load_config", lambda: {})


@pytest.fixture
def fixture_docs():
    """A tiny in-memory corpus: list of (base_path, title, body, repo, type, category)."""
    return [
        ("Notes/Nginx/cert-renew.md", "Nginx 憑證自動更新",
         "用 certbot 設定 nginx 的 TLS certificate 自動 renew。", "", "note", "Nginx"),
        ("Notes/Linux/oom.md", "Linux OOM killer 排查",
         "dmesg 看 out of memory，調整 oom_score_adj。", "", "note", "Linux"),
        ("Projects/libsynow3/oauth.md", "libsynow3 OAuth 流程",
         "libsynow3 的 token refresh 與 OAuth 授權實作。", "libsynow3", "project", "libsynow3"),
    ]
