from cortex_vec.eval import report


def test_scorecard_contains_adapter_table():
    summary = {
        "by_adapter": {
            "grep": {"n": 15, "p": 0.267, "r": 0.95, "mrr": 0.7, "hit_rate": 1.0, "latency_p50": 0.5},
            "hybrid": {"n": 15, "p": 0.578, "r": 0.967, "mrr": 0.88, "hit_rate": 1.0, "latency_p50": 14.0},
        },
        "by_type": {
            "hybrid/single-note": {"n": 10, "p": 0.6, "r": 1.0, "mrr": 0.9, "hit_rate": 1.0, "latency_p50": 13.0},
        },
    }
    md = report.render(summary, meta={"corpus": "cortex-vault-v1", "k": 5, "n": 15})
    assert "cortex-vault-v1" in md
    assert "| grep |" in md
    assert "| hybrid |" in md
    assert "0.578" in md
    assert "single-note" in md
