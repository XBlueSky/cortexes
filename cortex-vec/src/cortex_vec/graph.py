"""Wikilink graph over the vault, built lazily from markdown and cached per vault.

The vault's `[[Title]]` links form a human-curated graph. We resolve each link
target (a note title) to a base path via a title index (frontmatter `title`
plus the filename stem), then expose adjacency for graph-boosted retrieval.
Unresolved links are skipped (a dangling link is not an error).
"""
from pathlib import Path

from .parser import extract_wikilinks, parse_document

_cache = {}  # str(vault) -> adjacency dict


def build_graph(vault):
    """Return {base_path: set(neighbor_base_path)} for the vault. Cached by path."""
    key = str(vault)
    if key in _cache:
        return _cache[key]

    vault = Path(vault)
    title_to_path = {}
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
            title = fm.get("title", stem)
            title_to_path.setdefault(title, rel)
            title_to_path.setdefault(stem, rel)
            raw.append((rel, extract_wikilinks(body)))

    adjacency = {rel: set() for rel, _ in raw}
    for rel, targets in raw:
        for t in targets:
            dest = title_to_path.get(t)
            if dest and dest != rel:
                adjacency[rel].add(dest)
                adjacency.setdefault(dest, set()).add(rel)  # links are bidirectional

    _cache[key] = adjacency
    return adjacency


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


def boost(fused, adjacency, top_k=5, hops=1, weight=0.1):
    """Boost candidates that are wikilink-neighbors of the top-`top_k` hits.

    fused: [(doc_id, score)] best-first. Only candidates already in `fused` are
    boosted (no new docs introduced). Boost = weight / distance. Re-sorted.
    """
    if not fused or weight <= 0:
        return fused
    seeds = [doc_id for doc_id, _ in fused[:top_k]]
    dist = _bfs_neighbors(adjacency, seeds, hops)
    if not dist:
        return fused
    boosted = []
    for doc_id, score in fused:
        if doc_id in dist:
            score = score + weight / dist[doc_id]
        boosted.append((doc_id, score))
    boosted.sort(key=lambda kv: kv[1], reverse=True)
    return boosted
