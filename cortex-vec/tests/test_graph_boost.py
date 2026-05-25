from cortex_vec import graph


def test_boost_promotes_graph_neighbor():
    fused = [("a", 0.50), ("b", 0.40), ("c", 0.10)]
    adjacency = {"a": {"c"}, "c": {"a"}, "b": set()}
    out = graph.boost(fused, adjacency, top_k=1, hops=1, weight=0.5)
    scores = dict(out)
    assert scores["c"] > 0.10
    assert scores["a"] == 0.50
    ids = [i for i, _ in out]
    assert ids.index("c") < ids.index("b")


def test_boost_no_neighbors_noop():
    fused = [("a", 0.5), ("b", 0.4)]
    adjacency = {"a": set(), "b": set()}
    assert graph.boost(fused, adjacency, top_k=1, hops=1, weight=0.5) == fused
