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
        "repo": (repos or [""])[0],
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


def graph_stream(adjacency, seeds, hops=1, max_n=15):
    """A rank-based stream of wikilink-neighbors of `seeds`, nearest first.

    Returns [(doc_id, rank)] (rank 0-based, capped at max_n), excluding seeds —
    shaped for rrf_fuse as a third retrieval stream. Empty if no neighbors.
    """
    dist = _bfs_neighbors(adjacency, seeds, hops)
    if not dist:
        return []
    ordered = sorted(dist.items(), key=lambda kv: kv[1])  # nearest first
    return [(doc_id, rank) for rank, (doc_id, _d) in enumerate(ordered[:max_n])]
