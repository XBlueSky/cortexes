"""Every model call goes through providers: summary, eval propose, status, search notes."""
import json
import sys
import types

from cortex_vec import cli, config, errors, fusion, providers, store
from cortex_vec.eval import run


class _FakeChat:
    """A chat client: records each create() call, then answers or raises."""

    def __init__(self, content="ok", fail=None):
        self.calls, self._content, self._fail = [], content, fail
        self.chat = types.SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._fail:
            raise self._fail
        message = types.SimpleNamespace(content=self._content)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


class _Col:
    def count(self): return 0
    def get(self, include=None): return {"metadatas": []}


class _Client:
    def get_collection(self, name): return _Col()


def _status(monkeypatch, capsys, tmp_path, models, *flags):
    monkeypatch.setattr(config, "load_config",
                        lambda: {"vault_path": str(tmp_path), "models": models})
    monkeypatch.setattr(store, "get_client", lambda: _Client())
    monkeypatch.setattr(sys, "argv", ["cortex-vec", "status", *flags])
    cli.main()
    return capsys.readouterr().out


def test_brief_is_one_short_line():
    assert errors.brief(RuntimeError("first\nsecond")) == "RuntimeError: first"
    assert errors.brief(ValueError()) == "ValueError"
    assert len(errors.brief(RuntimeError("x" * 5000))) == len("RuntimeError: ") + 200


def test_summary_uses_the_shared_chat_client_and_model(monkeypatch):
    chat = _FakeChat("a summary")
    monkeypatch.setattr(providers, "chat_client", lambda: chat)
    monkeypatch.setattr(config, "load_config", lambda: {"models": {"chat": {"model": "my-chat-model"}}})
    assert store._generate_summary("T", "a,b", "body") == "a summary"
    call = chat.calls[0]
    assert call["model"] == "my-chat-model"
    assert call["max_completion_tokens"] == 400 and call["reasoning_effort"] == "none"


def test_summary_failure_falls_back_and_warns_once_per_process(monkeypatch, capsys):
    monkeypatch.setattr(store, "_summary_warned", False)
    monkeypatch.setattr(providers, "chat_client",
                        lambda: _FakeChat(fail=RuntimeError("boom\n<html>page</html>")))
    assert store._generate_summary("T", "a,b", "body") == "T. Tags: a,b"
    assert store._generate_summary("T2", "c", "body") == "T2. Tags: c"
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "summary generation failed (RuntimeError: boom)" in err and "title + tags" in err


def test_eval_propose_uses_the_shared_chat_client_and_model(tmp_path, monkeypatch):
    chat = _FakeChat("a query")
    monkeypatch.setattr(providers, "chat_client", lambda: chat)
    monkeypatch.setattr(run, "_load_corpus_docs",
                        lambda: [{"id": "Notes/a.md", "title": "A", "summary": "s"}])
    out = tmp_path / "q.jsonl"
    run._propose(types.SimpleNamespace(queries=str(out)))
    assert chat.calls[0]["model"] == "gpt-5.4-mini" and chat.calls[0]["max_completion_tokens"] == 40
    assert json.loads(out.read_text())["gold"] == ["Notes/a.md"]


def test_vector_note_names_the_configured_key_env(monkeypatch):
    monkeypatch.setattr(config, "load_config",
                        lambda: {"models": {"embedding": {"api_key_env": "MY_EMBED_KEY"}}})
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.delenv("MY_EMBED_KEY", raising=False)
    notes = []
    assert fusion._vector_stream("q", 5, None, notes) == []
    # "skipped", not "failed": the key is checked before the store is opened.
    assert notes == ["vector stream skipped (MY_EMBED_KEY not set); results are BM25-only"]


def test_a_vector_failure_note_stays_on_one_short_line(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")

    def gateway_error(query, n, where):
        raise RuntimeError("502 Bad Gateway " + "x" * 3000 + "\n<html>\n<body>down</body>")

    monkeypatch.setattr(store, "vector_stream", gateway_error)
    notes = []
    assert fusion._vector_stream("q", 5, None, notes) == []
    assert notes[0].startswith("vector stream failed (RuntimeError: 502 Bad Gateway")
    assert notes[0].endswith("results are BM25-only")
    assert "\n" not in notes[0] and len(notes[0]) < 300


def test_status_text_is_unchanged_without_models(monkeypatch, capsys, tmp_path):
    lines = _status(monkeypatch, capsys, tmp_path, {}).splitlines()
    assert "Embedding:  text-embedding-3-small (OpenAI)" in lines
    assert "Summary:    gpt-5.4-mini (OpenAI)" in lines


def test_status_reports_the_configured_models(monkeypatch, capsys, tmp_path):
    models = {"embedding": {"model": "my-embedding-model"},
              "chat": {"type": "azure", "model": "my-deployment",
                       "base_url": "https://chat.example.com", "api_version": "2024-06-01"}}
    lines = _status(monkeypatch, capsys, tmp_path, models).splitlines()
    assert "Embedding:  my-embedding-model (OpenAI)" in lines
    assert "Summary:    my-deployment (Azure OpenAI)" in lines
    doc = json.loads(_status(monkeypatch, capsys, tmp_path, models, "--json"))
    assert doc["embedding_model"] == "my-embedding-model" and doc["embedding_provider"] == "openai"
    assert doc["summary_model"] == "my-deployment" and doc["summary_provider"] == "azure"


def test_status_labels_the_http_type(monkeypatch, capsys, tmp_path):
    models = {"embedding": {"type": "http", "model": "my-embedding-model",
                            "base_url": "https://llm.example.com/v1"}}
    assert "Embedding:  my-embedding-model (HTTP endpoint)" in _status(
        monkeypatch, capsys, tmp_path, models)
    doc = json.loads(_status(monkeypatch, capsys, tmp_path, models, "--json"))
    assert doc["embedding_provider"] == "http"
