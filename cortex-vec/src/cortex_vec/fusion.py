"""Hybrid retrieval: RRF fusion of vector + BM25 streams."""
import os

from . import store
from .config import BM25_DIR, get_retrieval_config, get_vault_path


def rrf_fuse(ranked, weights, k=60):
    """Reciprocal Rank Fusion over named streams.

    ranked:  {stream_name: [(doc_id, rank), ...]}  (rank is 0-based, best=0)
    weights: {stream_name: weight}
    Returns [(doc_id, score)] sorted by score desc. Streams that are empty
    have their weight redistributed across the present streams.
    """
    present = [name for name, items in ranked.items() if items]
    if not present:
        return []
    total = sum(weights.get(name, 0.0) for name in present) or 1.0
    norm = {name: weights.get(name, 0.0) / total for name in present}

    scores = {}
    for name in present:
        for doc_id, rank in ranked[name]:
            scores[doc_id] = scores.get(doc_id, 0.0) + norm[name] * (1.0 / (k + rank + 1))
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def _bm25_stream(query, n, where, synonym_weight=0.0):
    """Load the persisted BM25 index and search; return [] on any failure."""
    from . import bm25
    try:
        idx = bm25.BM25Index(BM25_DIR)
        idx.load()
        return idx.search(query, n, where, synonym_weight=synonym_weight)
    except Exception:
        return []


def _vector_stream(query, n, where):
    # No API key -> embeddings unavailable; skip vector so the query degrades to
    # BM25-only. (The embedding fn hard-exits via sys.exit on a missing key, and
    # SystemExit is not caught by `except Exception`, so we must check up front.)
    if not os.environ.get("OPENAI_API_KEY"):
        return []
    try:
        return store.vector_stream(query, n, where)
    except Exception:
        return []


# Order matters: vector first so its display fields (e.g. summary) win on merge.
_STREAM_ORDER = ("vector", "bm25")


def _graph_boost(fused, rc):
    """Boost fused candidates by wikilink proximity to the top hits. Returns
    fused unchanged on any failure (e.g. vault not configured)."""
    from . import graph as graph_mod
    try:
        adjacency = graph_mod.build_graph(get_vault_path())
        return graph_mod.boost(
            fused, adjacency,
            top_k=rc["graph_top_k"], hops=rc["graph_hops"], weight=rc["graph_weight"],
        )
    except (Exception, SystemExit):
        return fused


def _diversify(fused, display, max_per_repo):
    """Cap results per repo: keep best-`max_per_repo` per repo first, then append
    the rest in original order (nothing dropped, only reordered). 0 = no-op.
    Docs with an empty repo are never capped.
    """
    if not max_per_repo:
        return fused
    counts = {}
    primary, overflow = [], []
    for doc_id, score in fused:
        repo = (display.get(doc_id) or {}).get("repo", "")
        if not repo:
            primary.append((doc_id, score))
            continue
        if counts.get(repo, 0) < max_per_repo:
            counts[repo] = counts.get(repo, 0) + 1
            primary.append((doc_id, score))
        else:
            overflow.append((doc_id, score))
    return primary + overflow


def search(query, n=5, where=None, use_bm25=True, use_vector=True, graph=None, rerank=None):
    """Hybrid search entry point. Returns up to n display dicts (best-first).

    Gracefully degrades: if a stream errors or is disabled, the other carries
    the query (RRF weight is redistributed in rrf_fuse).
    """
    rc = get_retrieval_config()
    weights = {"vector": rc["w_vec"], "bm25": rc["w_bm25"]}

    streams = {}
    if use_vector:
        streams["vector"] = _vector_stream(query, n, where)
    if use_bm25:
        streams["bm25"] = _bm25_stream(query, n, where, synonym_weight=rc["synonym_weight"])

    ranked = {}
    display = {}
    for name in _STREAM_ORDER:
        items = streams.get(name) or []
        for rank, item in enumerate(items):
            ranked.setdefault(name, []).append((item["id"], rank))
            disp = display.setdefault(item["id"], {})
            for key, val in item.items():
                if key == "score":
                    continue
                if key not in disp or not disp.get(key):
                    disp[key] = val

    fused = rrf_fuse(ranked, weights, k=rc["rrf_k"])
    use_graph = rc["graph"] if graph is None else graph
    if use_graph:
        fused = _graph_boost(fused, rc)
    fused = _diversify(fused, display, rc["max_per_repo"])

    use_rerank = rc["rerank"] if rerank is None else rerank
    take = max(n, rc["rerank_window"]) if use_rerank else n

    out = []
    for doc_id, score in fused[:take]:
        entry = dict(display.get(doc_id, {}))
        entry["id"] = doc_id
        entry["score"] = round(score, 6)
        out.append(entry)

    if use_rerank:
        from . import rerank as rerank_mod
        out = rerank_mod.rerank(query, out, model=rc["rerank_model"], window=rc["rerank_window"])

    return out[:n]
