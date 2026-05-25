from types import SimpleNamespace

from cortex_vec import store


def test_bm25_only_rebuild_skips_chromadb(tmp_path, monkeypatch):
    notes = tmp_path / "Notes" / "X"
    notes.mkdir(parents=True)
    (notes / "a.md").write_text(
        "---\ntitle: Alpha\n---\nnginx certificate renew\n", encoding="utf-8")
    (notes / "b.md").write_text(
        "---\ntitle: Beta\n---\noom killer dmesg\n", encoding="utf-8")

    monkeypatch.setattr(store, "get_vault_path", lambda: tmp_path)
    monkeypatch.setattr(store, "BM25_DIR", tmp_path / "bm25")

    def _boom():
        raise AssertionError("get_client must not be called in --bm25-only mode")

    monkeypatch.setattr(store, "get_client", _boom)

    store.cmd_rebuild(SimpleNamespace(bm25_only=True))

    idx = store.BM25Index(tmp_path / "bm25")
    idx.load()
    assert idx.count() == 2
    assert idx.search("nginx certificate", n=1)[0]["id"] == "Notes/X/a.md"
