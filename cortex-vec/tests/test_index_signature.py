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


@pytest.mark.parametrize("content", [
    "{not json",                              # cut off mid-write
    "",                                       # truncated to nothing
    '{"type": "openai"}',                     # a key is missing
    '["openai", "text-embedding-3-small"]',   # valid JSON, wrong shape
    '{"type": "openai", "model": 1}',         # a value is not a string
])
def test_an_unreadable_signature_file_counts_as_unmarked(client, content):
    _seed(store.get_collection(client))
    _sig_file().write_text(content)
    assert store.index_signature(client) == DEFAULT
    store.get_collection(client)                       # and it is no traceback either


def test_another_writers_temp_file_is_left_alone(client):
    # Two first-time writers must not share one temp name: the second would
    # move the first one's half-written file into place, or find it gone.
    store.VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
    theirs = _sig_file().with_name(store.SIGNATURE_FILE + ".tmp")
    theirs.write_text("half-writ")
    store.get_collection(client)
    assert json.loads(_sig_file().read_text()) == DEFAULT
    assert theirs.read_text() == "half-writ"
    assert sorted(p.name for p in store.VECTORSTORE_DIR.glob(store.SIGNATURE_FILE + "*")) == [
        store.SIGNATURE_FILE, store.SIGNATURE_FILE + ".tmp"]      # no temp of our own left behind


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


def test_status_warns_when_chroma_reports_a_conflict(client, tmp_path, monkeypatch, capsys):
    # No signature file and default settings, so the signatures agree; only
    # chroma knows the index came from another function. `search` and `upsert`
    # report that, and `status` has to say the same.
    _seed(client.get_or_create_collection(name=config.COLLECTION_NAME, embedding_function=_OtherEF(),
                                          metadata={"hnsw:space": "cosine"}))
    _use(monkeypatch, {}, vault_path=str(_vault(tmp_path)))
    _main(monkeypatch, "status", "--json")
    doc = json.loads(capsys.readouterr().out)
    assert any("cortex-test-other" in w and "cortex-vec rebuild" in w for w in doc["warnings"])
    assert not _sig_file().exists()                    # status only looks


def test_status_on_a_matching_index_has_no_mismatch_warning(client, tmp_path, monkeypatch, capsys):
    _seed(store.get_collection(client))
    _use(monkeypatch, {}, vault_path=str(_vault(tmp_path)))
    _main(monkeypatch, "status", "--json")
    assert not any("rebuild`" in w and "index was built" in w
                   for w in json.loads(capsys.readouterr().out)["warnings"])


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


def _bm25_only_note(monkeypatch):
    """A keyless setup: the note is in the BM25 index and there is no vector index."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    bm25 = BM25Index(store.BM25_DIR)
    bm25.build_from_docs([{"id": "Notes/a.md", "title": "A", "body": "body"}])
    bm25.save()


def _bm25_count():
    bm25 = BM25Index(store.BM25_DIR)
    bm25.load()
    return bm25.count()


def test_delete_without_a_vector_index_still_removes_the_bm25_entry(monkeypatch, capsys):
    _bm25_only_note(monkeypatch)
    _main(monkeypatch, "delete", "Notes/a.md", "--json")
    cap = capsys.readouterr()
    assert json.loads(cap.out) == {"deleted": 1, "path": "Notes/a.md"}
    assert "not indexed" not in cap.err
    assert _bm25_count() == 0


def test_a_bm25_only_delete_says_which_index_it_touched(monkeypatch, capsys):
    _bm25_only_note(monkeypatch)
    _main(monkeypatch, "delete", "Notes/a.md")
    cap = capsys.readouterr()
    assert cap.out.strip() == "Deleted: Notes/a.md from the BM25 index (no vector entries)"
    assert cap.err == ""


# ── the http type ────────────────────────────────────────────────────────────

HTTP = {"embedding": {"type": "http", "model": "my-embedding-model"}}
HTTP_SIG = {"type": "http", "model": "my-embedding-model"}


def test_an_http_index_records_the_function_name_and_the_model_only(client, monkeypatch):
    _use(monkeypatch, HTTP)
    col = store.get_collection(client)
    assert json.loads(_sig_file().read_text()) == HTTP_SIG
    assert col.configuration_json["embedding_function"] == {
        "type": "known", "name": "cortex-http", "config": {"model": "my-embedding-model"}}


def test_changing_only_the_endpoint_needs_no_rebuild(client, monkeypatch):
    _use(monkeypatch, HTTP)
    _seed(store.get_collection(client))
    _use(monkeypatch, {"embedding": {**HTTP["embedding"], "base_url": "http://127.0.0.1:9/other"}})
    assert store.get_collection(store.get_client()).count() == 2


@pytest.mark.parametrize("built, now, names", [
    ({}, HTTP, ("openai/text-embedding-3-small", "http/my-embedding-model")),
    (HTTP, {}, ("http/my-embedding-model", "openai/text-embedding-3-small")),
    # the same model name behind the other type is still another index
    (HTTP, {"embedding": {"model": "my-embedding-model"}},
     ("http/my-embedding-model", "openai/my-embedding-model")),
])
def test_switching_between_openai_and_http_is_a_mismatch(client, monkeypatch, built, now, names):
    _use(monkeypatch, built)
    _seed(store.get_collection(client))
    _use(monkeypatch, now)
    with pytest.raises(IndexMismatch) as exc:
        store.get_collection(client)
    rendered = exc.value.render()
    assert all(name in rendered for name in names) and "cortex-vec rebuild" in rendered


def test_a_lost_signature_file_does_not_let_openai_reuse_an_http_index(client, monkeypatch):
    _use(monkeypatch, HTTP)
    _seed(store.get_collection(client))
    _sig_file().unlink()                     # unmarked now counts as openai + the default model
    _use(monkeypatch, {})
    with pytest.raises(IndexMismatch) as exc:
        store.get_collection(client)
    assert "cortex-http" in exc.value.render() and "cortex-vec rebuild" in exc.value.render()


def test_delete_works_on_an_http_index_after_switching_away_and_without_a_key(client, monkeypatch, capsys):
    _use(monkeypatch, HTTP)
    _seed(store.get_collection(client))
    _use(monkeypatch, {})                    # openai now: a mismatch for search and upsert
    monkeypatch.delenv("OPENAI_API_KEY")
    _main(monkeypatch, "delete", "Notes/a.md", "--json")
    assert json.loads(capsys.readouterr().out) == {"deleted": 2, "path": "Notes/a.md"}
    assert store.open_existing_collection(store.get_client()).count() == 0


def test_status_on_an_http_index_and_after_switching_away(client, tmp_path, monkeypatch, capsys):
    root = _vault(tmp_path)
    _use(monkeypatch, HTTP, vault_path=str(root))
    _seed(store.get_collection(client))
    _main(monkeypatch, "status", "--json")
    doc = json.loads(capsys.readouterr().out)
    assert (doc["entries"], doc["embedding_provider"], doc["embedding_model"]) == (
        2, "http", "my-embedding-model")
    assert not any("index was built" in w for w in doc["warnings"])
    _use(monkeypatch, {}, vault_path=str(root))
    _main(monkeypatch, "status", "--json")
    assert any("http/my-embedding-model" in w and "cortex-vec rebuild" in w
               for w in json.loads(capsys.readouterr().out)["warnings"])


def test_rebuild_moves_an_openai_index_to_http(client, tmp_path, monkeypatch):
    _seed(store.get_collection(client))
    _use(monkeypatch, HTTP, vault_path=str(_vault(tmp_path)))   # empty vault: nothing to embed
    _main(monkeypatch, "rebuild")
    assert json.loads(_sig_file().read_text()) == HTTP_SIG
    col = store.get_collection(store.get_client())
    assert col.configuration_json["embedding_function"]["name"] == "cortex-http"
