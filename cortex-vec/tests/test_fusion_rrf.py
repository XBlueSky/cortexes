from cortex_vec import fusion


def test_rrf_basic_two_streams():
    ranked = {
        "vector": [("a", 0), ("b", 1)],
        "bm25": [("b", 0), ("c", 1)],
    }
    fused = fusion.rrf_fuse(ranked, {"vector": 0.6, "bm25": 0.4}, k=60)
    ids = [i for i, _ in fused]
    assert "b" in ids and "a" in ids and "c" in ids
    # b appears in both streams near the top -> should rank first
    assert ids[0] == "b"


def test_rrf_redistributes_weight_when_stream_empty():
    ranked = {"vector": [], "bm25": [("x", 0), ("y", 1)]}
    fused = fusion.rrf_fuse(ranked, {"vector": 0.6, "bm25": 0.4}, k=60)
    # bm25 alone -> x ranks above y, scores reflect full (normalized) weight
    assert [i for i, _ in fused] == ["x", "y"]
    assert fused[0][1] > 0


def test_rrf_empty_all():
    assert fusion.rrf_fuse({"vector": [], "bm25": []}, {"vector": 0.6, "bm25": 0.4}) == []
