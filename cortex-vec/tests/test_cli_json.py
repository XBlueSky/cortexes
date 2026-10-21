"""`--json` on the operational commands: one JSON document on stdout, nothing
an agent has to scrape out of aligned human text."""
import json
import sys

import pytest

from cortex_vec import cli, config, store
from cortex_vec.bm25 import BM25Index


class _FakeCollection:
    def __init__(self, metas=()):
        self._metas = list(metas)

    def count(self):
        return len(self._metas)

    def get(self, include=None):
        return {"metadatas": self._metas}

    def upsert(self, **kw):
        pass


class _FakeClient:
    def __init__(self, col):
        self._col = col

    def get_collection(self, name):
        return self._col


@pytest.fixture
def vault(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    (root / "Notes").mkdir(parents=True)
    monkeypatch.setattr(config, "load_config", lambda: {"vault_path": str(root)})
    return root


def _run(monkeypatch, capsys, *argv):
    monkeypatch.setattr(sys, "argv", ["cortex-vec", *argv])
    cli.main()
    return capsys.readouterr()


def test_status_json_reports_counts(vault, monkeypatch, capsys):
    col = _FakeCollection([{"entry_type": "body"}, {"entry_type": "summary"},
                           {"entry_type": "body"}])
    monkeypatch.setattr(store, "get_client", lambda: _FakeClient(col))
    idx = BM25Index(store.BM25_DIR)
    idx.build_from_docs([{"id": "Notes/a.md", "title": "a", "body": "x"}])
    idx.save()

    cap = _run(monkeypatch, capsys, "status", "--json")

    doc = json.loads(cap.out)
    assert doc["bm25_notes"] == 1
    assert doc["entries"] == 3
    assert doc["body_entries"] == 2 and doc["summary_entries"] == 1
    assert doc["vault"] == str(vault)
    assert doc["warnings"] == []


def test_status_json_carries_warnings_instead_of_stderr(vault, monkeypatch, capsys):
    # vectors present but BM25 empty (conftest's isolated index has no docs)
    col = _FakeCollection([{"entry_type": "body"}])
    monkeypatch.setattr(store, "get_client", lambda: _FakeClient(col))

    cap = _run(monkeypatch, capsys, "status", "--json")

    doc = json.loads(cap.out)
    assert len(doc["warnings"]) == 1 and "rebuild" in doc["warnings"][0]
    assert cap.err == ""


def test_upsert_json(vault, monkeypatch, capsys):
    (vault / "Notes" / "a.md").write_text("# a\nbody\n")
    monkeypatch.setattr(store, "get_client", lambda: None)
    monkeypatch.setattr(store, "get_collection", lambda client: _FakeCollection())
    monkeypatch.setattr(store, "_delete_stale_entries", lambda col, rel: [])
    monkeypatch.setattr(store, "_generate_summary", lambda *a: "summary")

    cap = _run(monkeypatch, capsys, "upsert", "Notes/a.md", "--json")

    assert json.loads(cap.out) == {"upserted": "Notes/a.md"}


def test_delete_json_counts_removed_entries(monkeypatch, capsys):
    monkeypatch.setattr(store, "get_client", lambda: None)
    monkeypatch.setattr(store, "get_collection", lambda client: None)
    monkeypatch.setattr(store, "_delete_stale_entries",
                        lambda col, rel: ["Notes/a.md", "Notes/a.md::summary"])

    cap = _run(monkeypatch, capsys, "delete", "Notes/a.md", "--json")

    assert json.loads(cap.out) == {"deleted": 2, "path": "Notes/a.md"}


def test_delete_json_of_unindexed_path_reports_zero(monkeypatch, capsys):
    monkeypatch.setattr(store, "get_client", lambda: None)
    monkeypatch.setattr(store, "get_collection", lambda client: None)
    monkeypatch.setattr(store, "_delete_stale_entries", lambda col, rel: [])

    cap = _run(monkeypatch, capsys, "delete", "Notes/never.md", "--json")

    assert json.loads(cap.out) == {"deleted": 0, "path": "Notes/never.md"}


def test_rebuild_bm25_only_json(vault, monkeypatch, capsys):
    (vault / "Notes" / "a.md").write_text("# a\nbody\n")
    (vault / "Notes" / "b.md").write_text("# b\nbody\n")

    cap = _run(monkeypatch, capsys, "rebuild", "--bm25-only", "--json")

    assert json.loads(cap.out) == {"bm25_notes": 2, "vector_entries": None}


def test_distill_queue_json_without_stat_lists_paths(tmp_path, monkeypatch, capsys):
    raw = tmp_path / "Raw"
    raw.mkdir()
    (raw / "a.md").write_text("undistilled\n")

    cap = _run(monkeypatch, capsys, "distill-queue", "--root", str(raw), "--json")

    assert json.loads(cap.out) == [str(raw / "a.md")]


def test_empty_distill_queue_json_is_an_empty_array_without_stderr(tmp_path, monkeypatch,
                                                                   capsys):
    raw = tmp_path / "Raw"
    raw.mkdir()

    cap = _run(monkeypatch, capsys, "distill-queue", "--root", str(raw), "--json")

    assert json.loads(cap.out) == []
    assert cap.err == ""
