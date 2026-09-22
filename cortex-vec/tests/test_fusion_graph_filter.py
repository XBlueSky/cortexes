"""The wikilink graph stream must obey the same `where` filter as the other streams.

Third defect in the `--repo` family (see
docs/specs/2026-05-27-distill-dedup-repo-filter-blindspot.md). `_graph_ranked`
was the only stream not handed `where`, so wikilink neighbours entered the
fused result set unfiltered. It stayed invisible because the leaked doc usually
lands in the tail of `fused`, and with `rerank` on, `take = max(n, window)`
pulls that tail into the LLM reranker — whose ordering is not deterministic.
Every test here therefore pins `rerank=False` so a leak fails every run, not
one run in three.

As with test_where_shape_lockstep.py, every `where` is built through the real
producer `store._build_where()`; a hand-written payload proves nothing.
"""
from cortex_vec import bm25, fusion, graph, store


def _vec(doc_id="seed.md"):
    return [{"id": doc_id, "score": 0.9, "title": "Seed", "type": "note",
             "repo": "", "repos": [], "category": "", "tags": "", "summary": ""}]


class _NoBM25:
    def __init__(self, *a, **k): pass
    def load(self): pass
    def search(self, *a, **k): return []


def _meta(doc_id, type, repos, category=""):
    """Graph meta as build_graph emits it: display `repo` plus the full `repos`."""
    return {"id": doc_id, "title": doc_id, "type": type,
            "repo": (repos or [""])[0], "repos": list(repos),
            "category": category or (repos or [""])[0],
            "tags": "", "summary": ""}


def _wire(monkeypatch, neighbours):
    """seed.md wikilinks to every doc in `neighbours` ({doc_id: meta})."""
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    adjacency = {"seed.md": set(neighbours)}
    for d in neighbours:
        adjacency[d] = {"seed.md"}
    monkeypatch.setattr(graph, "build_graph", lambda vault: (adjacency, dict(neighbours)))
    monkeypatch.setattr(fusion, "get_vault_path", lambda: "/fake/vault", raising=False)


def _ids(where, n=10):
    return [o["id"] for o in fusion.search("q", n=n, where=where, graph=True, rerank=False)]


def test_graph_does_not_leak_out_of_repo_projects(monkeypatch):
    """The original symptom: --repo X surfaced Projects/ pages of other repos."""
    _wire(monkeypatch, {
        "Projects/mine/a.md": _meta("Projects/mine/a.md", "project", ["mine"]),
        "Projects/other/b.md": _meta("Projects/other/b.md", "project", ["other"]),
    })
    ids = _ids(store._build_where(repo="mine"))
    assert "Projects/other/b.md" not in ids, (
        f"graph stream leaked an out-of-repo Project past --repo: {ids}"
    )
    assert "Projects/mine/a.md" in ids


def test_graph_keeps_cross_repo_notes(monkeypatch):
    """Notes/ stay cross-repo through the graph stream too, via the $or branch."""
    _wire(monkeypatch, {
        "Notes/Linux/n.md": _meta("Notes/Linux/n.md", "note", ["unrelated"], "Linux"),
    })
    assert "Notes/Linux/n.md" in _ids(store._build_where(repo="mine"))


def test_graph_honours_multi_repo_membership(monkeypatch):
    """A page listing several repos must pass --repo for ANY of them.

    graph's `_meta_for` kept only `repos[0]` as a singular `repo`; filtering on
    that alone would wrongly drop a page whose second repo is the one queried.
    """
    _wire(monkeypatch, {
        "Projects/first/m.md": _meta("Projects/first/m.md", "project", ["first", "second"]),
    })
    assert "Projects/first/m.md" in _ids(store._build_where(repo="second")), (
        "multi-repo page dropped because only repos[0] was consulted"
    )


def test_graph_honours_type_filter(monkeypatch):
    """The graph stream bypassed the whole `where`, not just the repo clause."""
    _wire(monkeypatch, {
        "Notes/Linux/n.md": _meta("Notes/Linux/n.md", "note", [], "Linux"),
        "Projects/mine/a.md": _meta("Projects/mine/a.md", "project", ["mine"]),
    })
    ids = _ids(store._build_where(type="project"))
    assert "Notes/Linux/n.md" not in ids, f"--type ignored by the graph stream: {ids}"


def test_graph_honours_category_filter(monkeypatch):
    _wire(monkeypatch, {
        "Notes/Linux/n.md": _meta("Notes/Linux/n.md", "note", [], "Linux"),
        "Notes/Nginx/g.md": _meta("Notes/Nginx/g.md", "note", [], "Nginx"),
    })
    ids = _ids(store._build_where(category="Linux"))
    assert "Notes/Nginx/g.md" not in ids, f"--category ignored by the graph stream: {ids}"
    assert "Notes/Linux/n.md" in ids


def test_graph_unfiltered_when_no_where(monkeypatch):
    """No filter means no narrowing -- the fix must not break plain searches."""
    _wire(monkeypatch, {
        "Projects/other/b.md": _meta("Projects/other/b.md", "project", ["other"]),
    })
    assert "Projects/other/b.md" in _ids(None)


def test_graph_meta_carries_full_repos_list():
    """Lock the meta shape: the singular `repo` alone caused the drift above."""
    from cortex_vec.graph import _meta_for
    fm = {"title": "T", "repos": "alpha,beta", "tags": ""}
    m = _meta_for("Projects/alpha/x.md", fm, "body")
    assert m["repos"] == ["alpha", "beta"], m
    assert m["repo"] == "alpha", m  # display field unchanged


def test_every_stream_receives_the_where_clause(monkeypatch):
    """Structural guard: no retrieval stream may be wired in unfiltered.

    The graph defect was not a wrong filter, it was a *missing* one — the
    stream was simply never handed `where`. A test per stream only ever covers
    the streams that exist today, so this one asserts the wiring itself: every
    stream helper `search()` calls must receive the caller's clause. A fourth
    stream added without it fails here rather than in someone's dedup run.
    """
    where = store._build_where(repo="mine")
    seen = {}

    def _rec(name, real, where_pos):
        def wrapper(*a, **k):
            if "where" in k:
                seen[name] = k["where"]
            else:
                # Absent entirely = the stream was wired in without the clause,
                # which is exactly the defect this guards. Record the absence
                # rather than raising IndexError, so the assertion below reports
                # *which* stream was left unfiltered.
                seen[name] = a[where_pos] if len(a) > where_pos else None
            return real(*a, **k)
        return wrapper

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    monkeypatch.setattr(graph, "build_graph", lambda vault: ({"seed.md": set()}, {}))
    monkeypatch.setattr(fusion, "get_vault_path", lambda: "/fake/vault", raising=False)

    monkeypatch.setattr(fusion, "_vector_stream", _rec("vector", fusion._vector_stream, 2))
    monkeypatch.setattr(fusion, "_bm25_stream", _rec("bm25", fusion._bm25_stream, 2))
    monkeypatch.setattr(fusion, "_graph_ranked", _rec("graph", fusion._graph_ranked, 4))

    fusion.search("q", n=3, where=where, graph=True, rerank=False)

    assert set(seen) == {"vector", "bm25", "graph"}, f"a stream was not exercised: {seen}"
    for name, got in seen.items():
        assert got == where, f"{name} stream did not receive the where clause: {got!r}"


def test_multi_repo_filter_through_the_real_meta_producer(monkeypatch):
    """The multi-repo path, end to end, with meta built by `_meta_for` itself.

    The behavioural test above hand-builds its meta dicts, so it stays green
    even if `_meta_for` regresses to storing only `repos[0]` — the same
    hand-written-fixture blind spot this spec keeps re-learning. This one
    parses real frontmatter through the real producer, so a regression in
    either the producer or the predicate fails it.
    """
    from cortex_vec.graph import _meta_for

    doc = "Projects/first/m.md"
    meta = {doc: _meta_for(doc, {"title": "M", "repos": "first,second", "tags": ""}, "body")}

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    monkeypatch.setattr(graph, "build_graph",
                        lambda vault: ({"seed.md": {doc}, doc: {"seed.md"}}, meta))
    monkeypatch.setattr(fusion, "get_vault_path", lambda: "/fake/vault", raising=False)

    assert doc in _ids(store._build_where(repo="second")), (
        "page listing `second` as a non-first repo was dropped by the graph filter"
    )
    assert doc in _ids(store._build_where(repo="first"))
    assert doc not in _ids(store._build_where(repo="third"))


def test_filter_applies_before_the_max_n_cut(monkeypatch):
    """Rejects must not consume the window.

    `graph_stream` caps at max_n. Filtering the capped list would hand a
    scoped query a window mostly full of rejects — worst when the filter is
    most selective, which is exactly when the stream is most useful. The
    predicate therefore runs before the cut.
    """
    # Equidistant neighbours are ordered by doc_id, so the `n*` ids sort ahead
    # of the `z*` ones: 12 rejects fill the max_n=10 window before a single
    # admissible neighbour is reached. Filtering after the cut yields nothing.
    nb = {f"n{i:02d}.md": _meta(f"n{i:02d}.md", "project", ["other"]) for i in range(12)}
    nb.update({f"z{i:02d}.md": _meta(f"z{i:02d}.md", "project", ["mine"]) for i in range(3)})
    _wire(monkeypatch, nb)

    ids = _ids(store._build_where(repo="mine"), n=5)
    assert any(i.startswith("z") for i in ids), (
        f"in-repo neighbours were crowded out of the window by rejected ones: {ids}"
    )


def test_graph_display_does_not_leak_the_repos_field(monkeypatch):
    """`repos` is a filter field; the other two streams never emit it.

    Graph meta has to carry it so the clause can be evaluated, but letting it
    reach the result dicts would make a hit's shape depend on which stream
    found it.
    """
    _wire(monkeypatch, {
        "Projects/mine/a.md": _meta("Projects/mine/a.md", "project", ["mine", "extra"]),
    })
    out = fusion.search("q", n=5, where=store._build_where(repo="mine"),
                        graph=True, rerank=False)
    hit = next(o for o in out if o["id"] == "Projects/mine/a.md")
    assert "repos" not in hit, f"filter field leaked into the result dict: {sorted(hit)}"
    assert hit["repo"] == "mine"


def test_graph_rejects_neighbours_with_no_metadata(monkeypatch):
    """Absence of metadata is not evidence of passing the filter."""
    _wire(monkeypatch, {"Projects/mine/a.md": _meta("Projects/mine/a.md", "project", ["mine"])})
    # A neighbour reachable in the graph but missing from `meta` entirely.
    adjacency = {"seed.md": {"Projects/mine/a.md", "ghost.md"},
                 "Projects/mine/a.md": {"seed.md"}, "ghost.md": {"seed.md"}}
    meta = {"Projects/mine/a.md": _meta("Projects/mine/a.md", "project", ["mine"])}
    monkeypatch.setattr(graph, "build_graph", lambda vault: (adjacency, meta))

    assert "ghost.md" not in _ids(store._build_where(repo="mine"))


def test_graph_neighbour_order_is_deterministic():
    """Equidistant neighbours must come back in a process-independent order.

    `_bfs_neighbors` walks adjacency *sets*, so the insertion order of `dist`
    varies with PYTHONHASHSEED. Sorting on distance alone is stable and so
    preserved that variation: the stream was irreproducible across processes
    even with the LLM reranker off, which is what made the original leak look
    intermittent rather than conditional.

    The tiebreak is a keyed digest, not the doc id -- see the anti-bias test
    below for why. This pins the contract in-process; the cross-process proof
    (same query under several PYTHONHASHSEED values) lives outside the suite.
    """
    from cortex_vec.graph import _tiebreak, graph_stream

    # Pin the digest itself. Asserting only that the output matches
    # sorted(names, key=_tiebreak) is circular: swap _tiebreak for the builtin
    # hash() and both sides move together, so the suite stays green while the
    # order varies with PYTHONHASHSEED again -- confirmed by mutation.
    assert _tiebreak("Notes/x/000.md").hex() == "7497b9d04e4ae340", (
        "the tiebreak digest changed; it must stay stable ACROSS processes, "
        "which rules out the PYTHONHASHSEED-salted builtin hash()"
    )

    names = {f"{c}.md" for c in "mbzaqrkhtd"}
    adjacency = {"seed.md": names}
    adjacency.update({n: {"seed.md"} for n in names})
    out = [doc for doc, _rank in graph_stream(adjacency, ["seed.md"], hops=1, max_n=20)]
    assert out == sorted(names, key=_tiebreak), f"order is not the documented one: {out}"
    assert set(out) == names, "determinism must not drop or add neighbours"


def test_truncation_does_not_favour_a_path_prefix():
    """The max_n cut must not systematically starve one part of the vault.

    With `graph_hops = 1` every neighbour is distance 1, so whatever breaks the
    tie *is* the truncation rule. Tie-breaking on the doc id made that rule
    "keep the lexicographically smallest N", and `Notes/` sorts before
    `Projects/` -- measured over 300 realistic 5-seed calls on the real vault,
    truncation fired on 70% of them and lifted `Notes/` from 46% of the
    candidates to 68% of the survivors. That is the opposite of what a
    `--repo`-scoped query wants, since those exist to surface a repo's
    `Projects/` pages.
    """
    from cortex_vec.graph import graph_stream
    notes = {f"Notes/x/{i:03d}.md" for i in range(40)}
    projects = {f"Projects/y/{i:03d}.md" for i in range(40)}
    names = notes | projects
    adjacency = {"seed.md": names}
    adjacency.update({n: {"seed.md"} for n in names})

    kept = [doc for doc, _rank in graph_stream(adjacency, ["seed.md"], hops=1, max_n=20)]
    kept_projects = sum(1 for d in kept if d.startswith("Projects/"))
    # An unbiased cut of 20 from a 50/50 pool keeps ~10 Projects pages; the
    # lexicographic rule kept 0. Assert well clear of both.
    assert kept_projects >= 5, (
        f"truncation favours one prefix: only {kept_projects}/20 survivors are Projects/"
    )


def test_keep_screens_the_answer_not_the_path(monkeypatch):
    """With hops>1 the filter judges what is returned, not what the walk crosses.

    `keep` runs on the BFS *output*, so a neighbour two hops out is admitted on
    its own merits even when the only route to it runs through a page the
    filter rejects. That is the intended reading -- the clause describes the
    answer set -- but it was previously untested, so nothing distinguished it
    from an oversight. Moot at the shipped `graph_hops = 1`; this pins the
    behaviour for whoever raises it.
    """
    far, mid = "Projects/mine/far.md", "Projects/other/mid.md"
    meta = {mid: _meta(mid, "project", ["other"]), far: _meta(far, "project", ["mine"])}
    adjacency = {"seed.md": {mid}, mid: {"seed.md", far}, far: {mid}}

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    monkeypatch.setattr(graph, "build_graph", lambda vault: (adjacency, meta))
    monkeypatch.setattr(fusion, "get_vault_path", lambda: "/fake/vault", raising=False)

    rc = dict(__import__("cortex_vec.config", fromlist=["x"]).get_retrieval_config())
    rc.update({"graph": True, "graph_hops": 2, "rerank": False})
    monkeypatch.setattr(fusion, "get_retrieval_config", lambda: rc, raising=False)

    ids = _ids(store._build_where(repo="mine"), n=5)
    assert far in ids, "an admissible 2-hop neighbour was dropped with its bridge"
    assert mid not in ids, "the rejected bridge page must not itself be returned"
