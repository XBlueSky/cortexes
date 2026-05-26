from cortex_vec import graph


def test_graph_stream_ranks_neighbors_by_distance():
    # a -> b -> c ; seed=a, hops=2 : b at dist 1 (rank 0), c at dist 2 (rank 1)
    adjacency = {"a": {"b"}, "b": {"a", "c"}, "c": {"b"}}
    stream = graph.graph_stream(adjacency, seeds=["a"], hops=2, max_n=10)
    ids = [doc_id for doc_id, _ in stream]
    assert ids[0] == "b"                       # nearest neighbor first
    assert "c" in ids                          # 2-hop neighbor included
    assert "a" not in ids                      # seed excluded
    assert [r for _, r in stream] == list(range(len(stream)))  # 0-based contiguous ranks


def test_graph_stream_no_neighbors_empty():
    assert graph.graph_stream({"a": set()}, seeds=["a"], hops=1) == []


def test_graph_stream_respects_max_n():
    adjacency = {"a": {"b", "c", "d", "e"}}
    stream = graph.graph_stream(adjacency, seeds=["a"], hops=1, max_n=2)
    assert len(stream) == 2
