"""The index remembers which embedding model built it, and refuses another one.

These tests run against a real chroma under tmp_path. Rows are added with
explicit `embeddings=`, so no embedding API is ever called.
"""
import json
import sys

import pytest
from chromadb.api.types import Documents, EmbeddingFunction
from chromadb.utils.embedding_functions import register_embedding_function

from cortex_vec import cli, config, fusion, store
from cortex_vec.bm25 import BM25Index
from cortex_vec.errors import EXIT_SETUP, IndexMismatch

# chroma warns that a key passed directly is not persisted, which is the point.
pytestmark = pytest.mark.filterwarnings("ignore:Direct api_key configuration:DeprecationWarning")

DEFAULT = {"type": "openai", "model": "text-embedding-3-small"}
OTHER = {"embedding": {"model": "my-embedding-model"}}
IDS = ["Notes/a.md", "Notes/a.md::summary"]


@register_embedding_function
class _OtherEF(EmbeddingFunction[Documents]):
    """A second embedding-function name, so chroma itself reports a conflict."""

    def __init__(self): pass
    def __call__(self, input): return [[0.0, 0.0, 0.0] for _ in input]
    @staticmethod
    def name(): return "cortex-test-other"
    def default_space(self): return "cosine"
    @staticmethod
    def build_from_config(config): return _OtherEF()
    def get_config(self): return {}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")   # the stock function is built offline
    return store.get_client()


def _seed(col):
    col.add(ids=IDS, embeddings=[[0.1, 0.2, 0.3], [0.3, 0.2, 0.1]], documents=["x", "y"],
            metadatas=[{"entry_type": "body"}, {"entry_type": "summary"}])


def _sig_file():
    return store.VECTORSTORE_DIR / store.SIGNATURE_FILE


def _use(monkeypatch, models, **extra):
    monkeypatch.setattr(config, "load_config", lambda: {"models": models, **extra})


def _vault(tmp_path):
    root = tmp_path / "vault"
    (root / "Notes").mkdir(parents=True)
    return root


def _main(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["cortex-vec", *argv])
    cli.main()


def test_creating_the_collection_records_the_signature(client):
    assert store.index_signature(client) is None
    store.get_collection(client)
    assert json.loads(_sig_file().read_text()) == DEFAULT


def test_an_unmarked_index_counts_as_the_default_model(client):
    _seed(store.get_collection(client))
    _sig_file().unlink()
    assert store.index_signature(client) == DEFAULT
    store.get_collection(client)                       # default config: no error, no rebuild


def test_an_unreadable_signature_file_counts_as_unmarked(client):
    _seed(store.get_collection(client))
    _sig_file().write_text("{not json")
    assert store.index_signature(client) == DEFAULT


def test_a_changed_model_is_refused_with_both_sides_and_the_fix(client, monkeypatch):
    _seed(store.get_collection(client))
    _use(monkeypatch, OTHER)
    with pytest.raises(IndexMismatch) as exc:
        store.get_collection(client)
    rendered = exc.value.render()
    assert exc.value.code == EXIT_SETUP
    assert "openai/text-embedding-3-small" in rendered and "openai/my-embedding-model" in rendered
    assert "config.json" in rendered and "cortex-vec rebuild" in rendered


def test_upsert_on_a_mismatched_index_exits_3_and_writes_nothing(client, tmp_path, monkeypatch, capsys):
    _seed(store.get_collection(client))
    root = _vault(tmp_path)
    (root / "Notes" / "b.md").write_text("# b\nbody\n")
    _use(monkeypatch, OTHER, vault_path=str(root))
    # If the refusal ever regresses, fail here instead of calling a real model.
    monkeypatch.setattr(store, "_generate_summary", lambda *a: pytest.fail("reached the model"))
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "upsert", "Notes/b.md")
    assert exc.value.code == 3
    assert "cortex-vec: error: index was built with" in capsys.readouterr().err
    assert sorted(store.open_existing_collection(client).get(include=[])["ids"]) == IDS
    assert json.loads(_sig_file().read_text()) == DEFAULT
    bm25 = BM25Index(store.BM25_DIR)
    bm25.load()
    assert bm25.count() == 0


def test_rebuild_clears_the_mismatch(client, tmp_path, monkeypatch):
    _seed(store.get_collection(client))
    _use(monkeypatch, OTHER, vault_path=str(_vault(tmp_path)))   # empty vault: nothing to embed
    _main(monkeypatch, "rebuild")
    assert json.loads(_sig_file().read_text()) == {"type": "openai", "model": "my-embedding-model"}
    store.get_collection(store.get_client())


def test_chromas_own_conflict_becomes_the_same_mismatch(client):
    # An index built by some other function, with no signature file: what a
    # user sees today as a raw ValueError.
    _seed(client.get_or_create_collection(name=config.COLLECTION_NAME, embedding_function=_OtherEF(),
                                          metadata={"hnsw:space": "cosine"}))
    with pytest.raises(IndexMismatch) as exc:
        store.get_collection(client)
    rendered = exc.value.render()
    assert exc.value.code == EXIT_SETUP
    assert "cortex-test-other" in rendered and "cortex-vec rebuild" in rendered


def test_search_skips_the_vector_stream_with_a_note(client, monkeypatch):
    _seed(store.get_collection(client))
    _use(monkeypatch, OTHER)
    notes = []
    assert fusion._vector_stream("q", 5, None, notes) == []      # raises before any query is embedded
    assert notes[0].startswith("vector stream skipped (index was built with")
    assert "cortex-vec rebuild" in notes[0] and notes[0].endswith("results are BM25-only")


def test_status_warns_on_mismatch(client, tmp_path, monkeypatch, capsys):
    _seed(store.get_collection(client))
    _use(monkeypatch, OTHER, vault_path=str(_vault(tmp_path)))
    _main(monkeypatch, "status", "--json")
    doc = json.loads(capsys.readouterr().out)
    assert doc["embedding_model"] == "my-embedding-model"
    assert any("text-embedding-3-small" in w and "cortex-vec rebuild" in w for w in doc["warnings"])


def test_delete_works_on_a_mismatched_index_without_any_key(client, monkeypatch, capsys):
    _seed(store.get_collection(client))
    _use(monkeypatch, OTHER)
    monkeypatch.delenv("OPENAI_API_KEY")
    _main(monkeypatch, "delete", "Notes/a.md", "--json")
    assert json.loads(capsys.readouterr().out) == {"deleted": 2, "path": "Notes/a.md"}
    assert store.open_existing_collection(store.get_client()).count() == 0


def test_delete_before_any_index_exists_is_a_no_op(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _main(monkeypatch, "delete", "Notes/never.md", "--json")
    cap = capsys.readouterr()
    assert json.loads(cap.out) == {"deleted": 0, "path": "Notes/never.md"} and "not indexed" in cap.err
    assert store.open_existing_collection(store.get_client()) is None    # nothing was created
