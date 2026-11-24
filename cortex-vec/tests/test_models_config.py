"""The `models` block of ~/.cortex/config.json: defaults, merging, validation.

A wrong block is a setup error (exit 3) on every command that uses a model,
even when the broken role is one that command would never have touched.
"""
import sys

import pytest

from cortex_vec import cli, config, store
from cortex_vec.errors import EXIT_SETUP, CliError


def _cfg(monkeypatch, models, **extra):
    monkeypatch.setattr(config, "load_config", lambda: {"models": models, **extra})


def test_defaults_when_models_is_absent():
    assert config.get_models_config() == {
        "embedding": {"type": "openai", "model": "text-embedding-3-small",
                      "base_url": None, "api_key_env": "OPENAI_API_KEY"},
        "chat": {"type": "openai", "model": "gpt-5.4-mini", "base_url": None,
                 "api_key_env": "OPENAI_API_KEY", "api_version": None},
    }


def test_each_role_merges_onto_its_own_defaults(monkeypatch):
    _cfg(monkeypatch, {"embedding": {"model": "my-embedding-model",
                                     "base_url": "https://llm.example.com/v1"}})
    mc = config.get_models_config()
    assert mc["embedding"] == {"type": "openai", "model": "my-embedding-model",
                               "base_url": "https://llm.example.com/v1",
                               "api_key_env": "OPENAI_API_KEY"}
    assert mc["chat"]["model"] == "gpt-5.4-mini"


def test_an_explicit_null_means_unset(monkeypatch):
    _cfg(monkeypatch, {"chat": {"model": None}})
    assert config.get_models_config()["chat"]["model"] == "gpt-5.4-mini"


@pytest.mark.parametrize("models", [None, {"chat": None}])
def test_a_null_block_or_role_means_unset_too(monkeypatch, models):
    _cfg(monkeypatch, models)
    assert config.get_models_config()["chat"]["model"] == "gpt-5.4-mini"


@pytest.mark.parametrize("models, field, names", [
    ({"rerank": {"type": "llm"}}, "models.rerank", "embedding, chat"),
    ({"chat": {"type": "anthropic"}}, "models.chat.type", "openai, azure"),
    ({"embedding": {"type": "azure"}}, "models.embedding.type", "valid values: openai"),
    ({"chat": {"type": "azure", "api_version": "2024-06-01"}}, "models.chat.base_url", "azure"),
    ({"chat": {"type": "azure", "base_url": "https://chat.example.com"}}, "models.chat.api_version", "azure"),
    ({"chat": {"api_version": "2024-06-01"}}, "models.chat.api_version", "openai"),
    ({"embedding": {"api_key": "sk-nope"}}, "models.embedding.api_key", "api_key_env"),
    ({"embedding": {"api_key_env": "sk-nope"}}, "models.embedding.api_key_env", "environment variable"),
    ({"chat": {"api_key_env": "sk-nope"}}, "models.chat.api_key_env", "environment variable"),
    ({"embedding": {"model": ""}}, "models.embedding.model", "non-empty string"),
    ({"chat": "gpt-5.4-mini"}, "models.chat", "object"),
    ("openai", "models", "object"),
])
def test_invalid_models_names_the_file_the_field_and_the_fix(monkeypatch, models, field, names):
    _cfg(monkeypatch, models)
    with pytest.raises(CliError) as exc:
        config.get_models_config()
    rendered = exc.value.render()
    assert exc.value.code == EXIT_SETUP
    assert "config.json" in rendered and field in rendered and names in rendered
    assert "sk-nope" not in rendered          # a pasted key is never echoed back


@pytest.mark.parametrize("argv", [
    ("search", "anything"), ("status",), ("delete", "Notes/a.md"),
    ("upsert", "Notes/a.md"), ("rebuild",),
    ("eval", "propose", "--queries", "q.jsonl"),
])
def test_a_bad_models_block_stops_every_model_command_before_it_runs(monkeypatch, capsys, argv):
    _cfg(monkeypatch, {"chat": {"type": "anthropic"}})   # a role most of these never touch
    monkeypatch.setattr(store, "get_client", lambda: pytest.fail("command body ran"))
    monkeypatch.setattr(sys, "argv", ["cortex-vec", *argv])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    err = capsys.readouterr().err
    assert exc.value.code == 3 and "models.chat.type" in err and err.count("\n") == 1


def test_bm25_only_rebuild_does_not_read_models(tmp_path, monkeypatch, capsys):
    root = tmp_path / "vault"
    (root / "Notes").mkdir(parents=True)
    _cfg(monkeypatch, {"chat": {"type": "anthropic"}}, vault_path=str(root))
    monkeypatch.setattr(sys, "argv", ["cortex-vec", "rebuild", "--bm25-only"])
    cli.main()
    assert "BM25: 0 notes indexed" in capsys.readouterr().out
