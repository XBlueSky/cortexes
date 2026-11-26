"""The `models` block of ~/.cortex/config.json: defaults, merging, validation.

A wrong block is a setup error (exit 3) on every command that uses a model,
even when the broken role is one that command would never have touched.
"""
import json
import re
import sys
from pathlib import Path

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
        "rerank": {"type": "llm", "model": None, "base_url": None, "api_key_env": "OPENAI_API_KEY"},
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


@pytest.mark.parametrize("models", [None, {"chat": None}, {"rerank": None}])
def test_a_null_block_or_role_means_unset_too(monkeypatch, models):
    _cfg(monkeypatch, models)
    mc = config.get_models_config()
    assert mc["chat"]["model"] == "gpt-5.4-mini" and mc["rerank"]["type"] == "llm"


@pytest.mark.parametrize("models, field, names", [
    ({"vision": {"type": "llm"}}, "models.vision", "embedding, chat, rerank"),
    ({"chat": {"type": "anthropic"}}, "models.chat.type", "openai, azure"),
    ({"embedding": {"type": "azure"}}, "models.embedding.type", "valid values: openai, http"),
    ({"chat": {"type": "http"}}, "models.chat.type", "openai, azure"),
    ({"chat": {"type": "azure", "api_version": "2024-06-01"}}, "models.chat.base_url", "azure"),
    ({"chat": {"type": "azure", "base_url": "https://chat.example.com"}}, "models.chat.api_version", "azure"),
    ({"chat": {"api_version": "2024-06-01"}}, "models.chat.api_version", "openai"),
    ({"embedding": {"api_key": "sk-nope"}}, "models.embedding.api_key", "api_key_env"),
    ({"embedding": {"api_key_env": "sk-nope"}}, "models.embedding.api_key_env", "environment variable"),
    ({"chat": {"api_key_env": "sk-nope"}}, "models.chat.api_key_env", "environment variable"),
    ({"embedding": {"model": ""}}, "models.embedding.model", "non-empty string"),
    ({"chat": "gpt-5.4-mini"}, "models.chat", "object"),
    ("openai", "models", "object"),
    ({"rerank": {"type": "cohere"}}, "models.rerank.type", "llm, endpoint"),
    ({"rerank": {"model": "my-rerank-model"}}, "models.rerank.model", "does not apply to type 'llm'"),
    ({"rerank": {"type": "llm", "base_url": "https://llm.example.com/v1"}}, "models.rerank.base_url", "fields for 'llm': none"),
    ({"rerank": {"api_key_env": "MY_RERANK_KEY"}}, "models.rerank.api_key_env", "llm"),
    ({"rerank": {"type": "endpoint", "api_key_env": "sk-nope"}}, "models.rerank.api_key_env", "environment variable"),
    ({"rerank": {"type": "endpoint", "base_url": "llm.example.com/v1"}}, "models.rerank.base_url", "http:// or https://"),
])
def test_invalid_models_names_the_file_the_field_and_the_fix(monkeypatch, models, field, names):
    _cfg(monkeypatch, models)
    with pytest.raises(CliError) as exc:
        config.get_models_config()
    rendered = exc.value.render()
    assert exc.value.code == EXIT_SETUP
    assert "config.json" in rendered and field in rendered and names in rendered
    assert "sk-nope" not in rendered          # a pasted key is never echoed back


@pytest.mark.parametrize("models, field, owner", [
    # `type` left at its default: the field is right, the type is missing.
    ({"rerank": {"base_url": "https://llm.example.com/v1"}}, "models.rerank.base_url",
     "type 'endpoint' takes base_url"),
    ({"chat": {"api_version": "2024-06-01"}}, "models.chat.api_version", "type 'azure' takes api_version"),
])
def test_a_field_of_another_type_names_that_type(monkeypatch, models, field, owner):
    _cfg(monkeypatch, models)
    with pytest.raises(CliError) as exc:
        config.get_models_config()
    rendered = exc.value.render()
    assert field in rendered and owner in rendered


HEX_KEY = "a3f1c09b7d2e4f6a8b0c1d2e3f405162"    # no prefix, no punctuation: shaped like an identifier


@pytest.mark.parametrize("role, extra", [
    ("embedding", {}),
    ("chat", {"type": "azure", "base_url": "https://chat.example.com", "api_version": "2024-06-01"}),
])
def test_a_key_that_looks_like_an_identifier_is_still_refused_unechoed(monkeypatch, role, extra):
    # Later messages print the name ("<name> not set"), and stderr ends up in
    # session records, so a pasted key has to stop here.
    _cfg(monkeypatch, {role: {**extra, "api_key_env": HEX_KEY}})
    with pytest.raises(CliError) as exc:
        config.get_models_config()
    rendered = exc.value.render()
    assert exc.value.code == EXIT_SETUP
    assert f"models.{role}.api_key_env" in rendered and "uppercase" in rendered
    assert HEX_KEY not in rendered


@pytest.mark.parametrize("name", ["OPENAI_API_KEY", "MY_GATEWAY_KEY", "_KEY2"])
def test_conventional_env_var_names_are_accepted(monkeypatch, name):
    _cfg(monkeypatch, {"embedding": {"api_key_env": name}})
    assert config.get_models_config()["embedding"]["api_key_env"] == name


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


GATEWAY = "https://llm.example.com/v1"


def test_http_is_a_valid_embedding_type(monkeypatch):
    _cfg(monkeypatch, {"embedding": {"type": "http", "model": "my-embedding-model",
                                     "base_url": GATEWAY, "api_key_env": "MY_EMBED_KEY"}})
    assert config.get_models_config()["embedding"] == {
        "type": "http", "model": "my-embedding-model", "base_url": GATEWAY,
        "api_key_env": "MY_EMBED_KEY"}


def test_http_base_url_falls_back_to_OPENAI_BASE_URL_and_the_block_wins(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://other.example.com/v1")
    _cfg(monkeypatch, {"embedding": {"type": "http"}})
    assert config.get_models_config()["embedding"]["base_url"] == "https://other.example.com/v1"
    _cfg(monkeypatch, {"embedding": {"type": "http", "base_url": GATEWAY}})
    assert config.get_models_config()["embedding"]["base_url"] == GATEWAY


def test_openai_base_url_is_still_left_to_the_sdk(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://other.example.com/v1")
    models = config.get_models_config()
    assert models["embedding"]["base_url"] is None and models["chat"]["base_url"] is None


@pytest.mark.parametrize("env_value", [None, ""])
def test_http_without_any_base_url_is_a_setup_error(monkeypatch, env_value):
    if env_value is None:
        monkeypatch.delenv("OPENAI_BASE_URL")
    else:
        monkeypatch.setenv("OPENAI_BASE_URL", env_value)
    _cfg(monkeypatch, {"embedding": {"type": "http"}})
    with pytest.raises(CliError) as exc:
        config.get_models_config()
    rendered = exc.value.render()
    assert exc.value.code == EXIT_SETUP
    assert "models.embedding.base_url" in rendered and "'http'" in rendered
    assert "OPENAI_BASE_URL" in rendered


@pytest.mark.parametrize("bad", [
    "llm.example.com/v1",                       # no scheme
    "https://",                                 # no host
    "https:///v1",
    "https://[::1/v1",                          # does not parse
    "https://llm.example.com:port/v1",          # not a port
    "https://llm.example.com/v1\n",             # a line ending
    "https://llm.example.com/v1 ",
    "https://llm.example.com/my models/v1",
])
@pytest.mark.parametrize("source", ["block", "env"])
def test_http_base_url_must_be_an_http_url_and_is_not_echoed(monkeypatch, source, bad):
    # Caught here, or `rebuild` deletes the index before the first request fails.
    monkeypatch.setenv("OPENAI_BASE_URL", bad if source == "env" else GATEWAY)
    _cfg(monkeypatch, {"embedding": {"type": "http", **({"base_url": bad} if source == "block" else {})}})
    with pytest.raises(CliError) as exc:
        config.get_models_config()
    rendered = exc.value.render()
    assert exc.value.code == EXIT_SETUP
    assert "models.embedding.base_url" in rendered and "http:// or https://" in rendered
    assert "example" not in rendered


@pytest.mark.parametrize("good", [
    "http://127.0.0.1:8080/v1",
    "http://[::1]:8080/v1",
    "HTTPS://llm.example.com",
    "https://llm.example.com/v1?code=abc",
])
def test_http_base_url_accepts_hosts_ports_and_queries(monkeypatch, good):
    _cfg(monkeypatch, {"embedding": {"type": "http", "base_url": good}})
    assert config.get_models_config()["embedding"]["base_url"] == good


@pytest.mark.parametrize("argv", [("rebuild",), ("upsert", "Notes/a.md"), ("search", "anything")])
def test_http_without_a_base_url_stops_the_command_before_it_touches_the_index(monkeypatch, capsys, argv):
    # `rebuild` deletes the collection first, so this has to fail before the command body.
    monkeypatch.delenv("OPENAI_BASE_URL")
    _cfg(monkeypatch, {"embedding": {"type": "http"}})
    monkeypatch.setattr(store, "get_client", lambda: pytest.fail("command body ran"))
    monkeypatch.setattr(sys, "argv", ["cortex-vec", *argv])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    err = capsys.readouterr().err
    assert exc.value.code == 3 and "models.embedding.base_url" in err and err.count("\n") == 1


def test_rerank_endpoint_base_url_falls_back_to_OPENAI_BASE_URL_and_the_block_wins(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example.com/v1")
    _cfg(monkeypatch, {"rerank": {"type": "endpoint"}})
    assert config.get_models_config()["rerank"]["base_url"] == "https://env.example.com/v1"
    _cfg(monkeypatch, {"rerank": {"type": "endpoint", "base_url": "https://llm.example.com/v1"}})
    assert config.get_models_config()["rerank"]["base_url"] == "https://llm.example.com/v1"


@pytest.mark.parametrize("argv", [["search", "x"], ["status"]])
def test_rerank_endpoint_without_any_base_url_stops_the_command_before_it_runs(monkeypatch, capsys, argv):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    _cfg(monkeypatch, {"rerank": {"type": "endpoint"}})          # rerank is not even turned on
    monkeypatch.setattr(store, "get_client", lambda: pytest.fail("command body ran"))
    monkeypatch.setattr(sys, "argv", ["cortex-vec", *argv])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    err = capsys.readouterr().err
    assert exc.value.code == EXIT_SETUP and "models.rerank.base_url" in err and err.count("\n") == 1


def test_retrieval_rerank_model_belongs_to_the_llm_type(monkeypatch):
    _cfg(monkeypatch, {"rerank": {"type": "endpoint", "base_url": "https://llm.example.com/v1"}},
         retrieval={"rerank_model": "pinned"})
    with pytest.raises(CliError) as exc:
        config.get_models_config()
    assert exc.value.code == EXIT_SETUP and "retrieval.rerank_model" in exc.value.render()
    _cfg(monkeypatch, {"rerank": {"type": "llm"}}, retrieval={"rerank_model": "pinned"})
    assert config.get_models_config()["rerank"]["type"] == "llm"


@pytest.mark.parametrize("value", [None, ""])
def test_an_empty_retrieval_rerank_model_is_unset_for_the_endpoint_type_too(monkeypatch, value):
    # fusion.search reads it as `rc["rerank_model"] or providers.chat_model()`,
    # so "" sets nothing and is no reason to stop.
    _cfg(monkeypatch, {"rerank": {"type": "endpoint", "base_url": "https://llm.example.com/v1"}},
         retrieval={"rerank_model": value})
    assert config.get_models_config()["rerank"]["type"] == "endpoint"


@pytest.mark.parametrize("readme", ["README.md", "README.zh-TW.md"])
def test_the_readme_defaults_block_is_a_valid_config(monkeypatch, readme):
    # Readers copy this block into config.json as a starting point.
    text = (Path(__file__).resolve().parents[2] / readme).read_text(encoding="utf-8")
    section = text[text.index("### Models"):]
    block = re.search(r"```json\n(.*?)\n```", section, re.S).group(1)
    monkeypatch.setattr(config, "load_config", lambda: json.loads(block))
    config.get_models_config()
