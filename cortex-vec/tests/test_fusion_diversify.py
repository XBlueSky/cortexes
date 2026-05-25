from cortex_vec import fusion


def test_diversify_caps_per_repo():
    fused = [("a", 0.9), ("b", 0.8), ("c", 0.7), ("d", 0.6)]
    display = {
        "a": {"repo": "X"}, "b": {"repo": "X"}, "c": {"repo": "X"}, "d": {"repo": "Y"},
    }
    out = fusion._diversify(fused, display, max_per_repo=2)
    ids = [i for i, _ in out]
    assert ids[:3] == ["a", "b", "d"]
    assert set(ids) == {"a", "b", "c", "d"}


def test_diversify_zero_is_noop():
    fused = [("a", 0.9), ("b", 0.8)]
    display = {"a": {"repo": "X"}, "b": {"repo": "X"}}
    assert fusion._diversify(fused, display, max_per_repo=0) == fused
