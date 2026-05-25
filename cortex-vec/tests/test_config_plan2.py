from cortex_vec import config


def test_plan2_retrieval_defaults(monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: {})
    rc = config.get_retrieval_config()
    assert rc["synonym_weight"] == 0.0
    assert rc["graph"] is False
    assert rc["graph_hops"] == 1
    assert rc["graph_weight"] == 0.1
    assert rc["graph_top_k"] == 5
    assert rc["rerank"] is False
    assert rc["rerank_model"] == "gpt-5.4-mini"
    assert rc["rerank_window"] == 15
    assert rc["rrf_k"] == 60
    assert rc["max_per_repo"] == 0


def test_plan2_override(monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: {"retrieval": {"graph": True, "synonym_weight": 0.7}})
    rc = config.get_retrieval_config()
    assert rc["graph"] is True
    assert rc["synonym_weight"] == 0.7
    assert rc["rerank"] is False
