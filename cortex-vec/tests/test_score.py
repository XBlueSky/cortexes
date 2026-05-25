from cortex_vec.eval import score


def test_precision_recall_hit():
    ranked = ["a", "b", "c", "d", "e"]
    gold = {"a", "x"}
    r = score.score_query(ranked, gold, k=5)
    assert r["precision_at_k"] == 1 / 5
    assert r["recall_at_k"] == 1 / 2
    assert r["hit"] is True
    assert r["reciprocal_rank"] == 1.0  # gold "a" at rank 1


def test_first_gold_rank_two():
    ranked = ["b", "a", "c"]
    r = score.score_query(ranked, {"a"}, k=3)
    assert r["reciprocal_rank"] == 0.5


def test_no_hit():
    r = score.score_query(["b", "c"], {"a"}, k=2)
    assert r["hit"] is False
    assert r["reciprocal_rank"] == 0.0
    assert r["precision_at_k"] == 0.0


def test_aggregate_by_adapter():
    rows = [
        {"adapter": "grep", "type": "x", "precision_at_k": 0.2, "recall_at_k": 1.0,
         "reciprocal_rank": 1.0, "hit": True, "latency_ms": 1.0},
        {"adapter": "grep", "type": "y", "precision_at_k": 0.4, "recall_at_k": 0.5,
         "reciprocal_rank": 0.5, "hit": True, "latency_ms": 3.0},
    ]
    agg = score.aggregate(rows)
    g = agg["by_adapter"]["grep"]
    assert g["n"] == 2
    assert abs(g["p"] - 0.3) < 1e-9
    assert abs(g["r"] - 0.75) < 1e-9
    assert abs(g["mrr"] - 0.75) < 1e-9
    assert g["hit_rate"] == 1.0
    assert g["latency_p50"] == 2.0
