"""Wikilink graph over the vault, built lazily from markdown and cached per vault.

The vault's `[[Title]]` links form a human-curated graph. We resolve each link
target (a note title) to a base path via a title index (frontmatter `title`
plus the filename stem), then expose:
  - `adjacency` {base_path: set(neighbor_base_path)} for traversal, and
  - `meta` {base_path: display dict} so graph-introduced neighbors can be shown.
Unresolved links are skipped (a dangling link is not an error).

Graph participates in retrieval as a THIRD RRF stream (see fusion.py): a
rank-based list of wikilink-neighbors of the top hits. Rank-based fusion avoids
the scale conflict of adding a boost onto RRF's compressed score band.
"""
import hashlib
from pathlib import Path

from .parser import classify_path, extract_summary, extract_wikilinks, parse_document

_cache = {}  # str(vault) -> (adjacency, meta)


def _meta_for(rel, fm, body):
    """Display dict for a note (mirrors the shape store/bm25 streams emit)."""
    doc_type, category = classify_path(rel)
    repos_str = fm.get("repos", "")
    repos = [r.strip() for r in repos_str.split(",") if r.strip()] if repos_str else []
    if doc_type == "project" and category and category not in repos:
        repos.insert(0, category)
    return {
        "id": rel,
        "title": fm.get("title", rel.rsplit("/", 1)[-1].removesuffix(".md")),
        "type": doc_type,
        # `repo` is the display field (first membership); `repos` is the full
        # membership list the `where` evaluator reads. Keeping only the singular
        # form let a multi-repo page fail a filter naming its second repo.
        "repo": (repos or [""])[0],
        "repos": repos,
        "category": category,
        "tags": fm.get("tags", ""),
        "summary": extract_summary(body),
    }


def build_graph(vault):
    """Return (adjacency, meta) for the vault. Cached by vault path."""
    key = str(vault)
    if key in _cache:
        return _cache[key]

    vault = Path(vault)
    title_to_path = {}
    meta = {}
    raw = []  # (base_path, [link targets])

    for scan_dir in ("Notes", "Projects"):
        base = vault / scan_dir
        if not base.is_dir():
            continue
        for md in base.rglob("*.md"):
            rel = str(md.relative_to(vault))
            if "_archive" in rel:
                continue
            text = md.read_text(encoding="utf-8", errors="replace")
            fm, body = parse_document(text)
            stem = md.stem
            title_to_path.setdefault(fm.get("title", stem), rel)
            title_to_path.setdefault(stem, rel)
            meta[rel] = _meta_for(rel, fm, body)
            raw.append((rel, extract_wikilinks(body)))

    adjacency = {rel: set() for rel, _ in raw}
    for rel, targets in raw:
        for t in targets:
            dest = title_to_path.get(t)
            if dest and dest != rel:
                adjacency[rel].add(dest)
                adjacency.setdefault(dest, set()).add(rel)  # links are bidirectional

    _cache[key] = (adjacency, meta)
    return _cache[key]


def _tiebreak(doc_id):
    """Stable, path-insensitive ordering key for equidistant neighbours.

    blake2b rather than `hash()`: the builtin is salted per process by
    PYTHONHASHSEED, which is the non-determinism this exists to remove.
    """
    return hashlib.blake2b(doc_id.encode("utf-8"), digest_size=8).digest()


def _bfs_neighbors(adjacency, seeds, hops):
    """Return {base_path: distance} reachable within `hops` from seeds (excluding seeds)."""
    frontier = set(seeds)
    visited = set(seeds)
    dist = {}
    for d in range(1, hops + 1):
        nxt = set()
        for node in frontier:
            for nb in adjacency.get(node, ()):
                if nb not in visited:
                    visited.add(nb)
                    dist[nb] = d
                    nxt.add(nb)
        frontier = nxt
        if not frontier:
            break
    return dist


def graph_stream(adjacency, seeds, hops=1, max_n=15, keep=None):
    """A rank-based stream of wikilink-neighbors of `seeds`, nearest first.

    Returns [(doc_id, rank)] (rank 0-based, capped at max_n), excluding seeds —
    shaped for rrf_fuse as a third retrieval stream. Empty if no neighbors.

    `keep` is an optional predicate on doc_id applied BEFORE the max_n cut, so a
    filtered query still gets a full window of admissible neighbours rather than
    a window thinned by rejects. It carries the caller's `where` clause: without
    it this stream was the one path into the fused set that no filter reached.

    `keep` screens what is RETURNED, not what the walk may cross. With
    `graph_hops > 1` a neighbour reachable only *through* a page the filter
    rejects is still returned if it passes itself. That is deliberate — the
    clause describes the answer set, not the path — but it means raising
    `graph_hops` widens what a scoped query can reach. Moot at the current
    `graph_hops = 1`, where there are no intermediate nodes.
    """
    dist = _bfs_neighbors(adjacency, seeds, hops)
    if not dist:
        return []
    # Tie-break deterministically, but NOT on the doc id itself. `dist` is
    # populated by iterating adjacency *sets*, so equidistant neighbours arrive
    # in an order that varies with PYTHONHASHSEED, and sorting on distance alone
    # is stable -- it preserved that variation, leaving the stream irreproducible
    # across processes. Ordering by doc id fixes that but buys a worse problem:
    # at graph_hops=1 every neighbour is distance 1, so the id becomes the sole
    # key and the max_n cut degenerates into "keep the lexicographically smallest
    # N". `Notes/` sorts before `Projects/`, so scoped queries -- the ones that
    # exist to surface a repo's Projects/ pages -- were the worst affected.
    # Measured over 300 realistic 5-seed calls: truncation fired on 70% of them
    # and lifted Notes/ from 46% of the candidates to 68% of the survivors.
    # A keyed digest is reproducible across processes like the id, without
    # correlating to the path prefix.
    ordered = sorted(dist.items(), key=lambda kv: (kv[1], _tiebreak(kv[0])))  # nearest first
    if keep is not None:
        ordered = [item for item in ordered if keep(item[0])]
    return [(doc_id, rank) for rank, (doc_id, _d) in enumerate(ordered[:max_n])]
