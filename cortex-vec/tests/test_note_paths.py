"""`upsert` and `delete` index a note under its vault-relative path.

`rebuild` derives every id from the path relative to the vault root. `upsert`
used to take the path as given, so an absolute one became the id itself and
the note sat in the index twice, or only under that absolute id.

Real chroma under tmp_path; embeddings come from `embedding_endpoint`.
"""
import sys

import pytest

from cortex_vec import cli, config, store
from cortex_vec.bm25 import BM25Index


@pytest.fixture
def vault(tmp_path, monkeypatch, embedding_endpoint):
    root = tmp_path / "vault"
    (root / "Notes").mkdir(parents=True)
    (root / "Notes" / "a.md").write_text("---\ntitle: A\n---\nbody of a\n", encoding="utf-8")
    models = {"embedding": {"type": "http", "model": "my-embedding-model",
                            "api_key_env": "MY_EMBED_KEY"}}
    monkeypatch.setattr(config, "load_config", lambda: {"models": models, "vault_path": str(root)})
    monkeypatch.setenv("MY_EMBED_KEY", "k-test-123")
    monkeypatch.setattr(store, "_generate_summary", lambda title, tags, body: f"{title} summary")
    embedding_endpoint()
    return root


def _cli(monkeypatch, capsys, *argv):
    monkeypatch.setattr(sys, "argv", ["cortex-vec", *argv])
    cli.main()
    return capsys.readouterr().out


def _vector_ids():
    return sorted(store.get_collection(store.get_client()).get(include=[])["ids"])


def _bm25_ids():
    index = BM25Index(store.BM25_DIR)
    index.load()
    return sorted(d["id"] for d in index.docs)


def _plant_absolute_entries(vault):
    # What `cortex-vec upsert /abs/path` used to leave behind.
    legacy = str(vault / "Notes" / "a.md")
    store.get_collection(store.get_client()).upsert(
        ids=[legacy, f"{legacy}::summary"], documents=["body of a", "A summary"])
    index = BM25Index(store.BM25_DIR)
    index.load()
    index.upsert(store.bm25_doc_from_fields(legacy, {"title": "A"}, "body of a"))
    index.save()


RELATIVE = ["Notes/a.md", "Notes/a.md::summary"]


@pytest.mark.parametrize("given", ["{vault}/Notes/a.md", "./Notes/a.md", "Notes/../Notes/a.md"])
def test_upsert_indexes_the_note_under_its_vault_relative_path(vault, monkeypatch, capsys, given):
    out = _cli(monkeypatch, capsys, "upsert", given.format(vault=vault))
    assert out == "Upserted: Notes/a.md\n"
    assert _vector_ids() == RELATIVE
    assert _bm25_ids() == ["Notes/a.md"]


@pytest.mark.parametrize("where", ["absolute", "relative"])
def test_upsert_of_a_path_outside_the_vault_is_a_caller_error(vault, tmp_path, monkeypatch, capsys, where):
    (tmp_path / "elsewhere.md").write_text("# elsewhere\n", encoding="utf-8")
    given = str(tmp_path / "elsewhere.md") if where == "absolute" else "../elsewhere.md"
    monkeypatch.setattr(sys, "argv", ["cortex-vec", "upsert", given])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    err = capsys.readouterr().err
    assert exc.value.code == 2
    assert given in err and "outside the vault" in err and str(vault) in err
    assert _bm25_ids() == []


def test_upsert_clears_what_an_absolute_path_left_behind(vault, monkeypatch, capsys):
    _plant_absolute_entries(vault)
    _cli(monkeypatch, capsys, "upsert", "Notes/a.md")
    assert _vector_ids() == RELATIVE
    assert _bm25_ids() == ["Notes/a.md"]


def test_delete_by_absolute_path_removes_the_note(vault, monkeypatch, capsys):
    _cli(monkeypatch, capsys, "upsert", "Notes/a.md")
    out = _cli(monkeypatch, capsys, "delete", str(vault / "Notes" / "a.md"))
    assert out == "Deleted: 2 entries for Notes/a.md\n"
    assert _vector_ids() == [] and _bm25_ids() == []


def test_delete_also_removes_what_an_absolute_path_left_behind(vault, monkeypatch, capsys):
    _cli(monkeypatch, capsys, "upsert", "Notes/a.md")
    _plant_absolute_entries(vault)
    out = _cli(monkeypatch, capsys, "delete", "Notes/a.md")
    assert out == "Deleted: 4 entries for Notes/a.md\n"
    assert _vector_ids() == [] and _bm25_ids() == []
