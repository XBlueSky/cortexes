from cortex_vec import graph


def _make_vault(tmp_path):
    notes = tmp_path / "Notes" / "X"
    notes.mkdir(parents=True)
    (notes / "a.md").write_text(
        "---\ntitle: Alpha\n---\nlinks to [[Beta]]\n", encoding="utf-8")
    (notes / "b.md").write_text(
        "---\ntitle: Beta\n---\nlinks to [[Alpha]] and [[Ghost]]\n", encoding="utf-8")
    return tmp_path


def test_build_graph_resolves_titles_to_paths(tmp_path):
    vault = _make_vault(tmp_path)
    adjacency = graph.build_graph(vault)
    assert "Notes/X/b.md" in adjacency["Notes/X/a.md"]
    assert "Notes/X/a.md" in adjacency["Notes/X/b.md"]
    assert all("Ghost" not in v for v in adjacency.values())


def test_build_graph_cached(tmp_path):
    vault = _make_vault(tmp_path)
    g1 = graph.build_graph(vault)
    g2 = graph.build_graph(vault)
    assert g1 is g2
