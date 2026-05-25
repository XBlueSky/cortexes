from cortex_vec import config


def test_retrieval_defaults(monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: {})
    rc = config.get_retrieval_config()
    assert rc["rrf_k"] == 60
    assert rc["w_bm25"] == 0.4
    assert rc["w_vec"] == 0.6
    assert rc["max_per_repo"] == 0


def test_retrieval_override(monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: {"retrieval": {"w_bm25": 0.7}})
    rc = config.get_retrieval_config()
    assert rc["w_bm25"] == 0.7
    assert rc["w_vec"] == 0.6  # untouched default preserved


def test_bm25_dir_exists():
    assert str(config.BM25_DIR).endswith("/.cortex/bm25")
