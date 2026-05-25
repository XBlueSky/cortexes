"""Hybrid retrieval: RRF fusion of vector + BM25 streams."""
from . import store
from .config import BM25_DIR, get_retrieval_config


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


def _bm25_stream(query, n, where):
    """Load the persisted BM25 index and search; return [] on any failure."""
    from . import bm25
    try:
        idx = bm25.BM25Index(BM25_DIR)
        idx.load()
        return idx.search(query, n, where)
    except Exception:
        return []


def _vector_stream(query, n, where):
    try:
        return store.vector_stream(query, n, where)
    except Exception:
        return []


# Order matters: vector first so its display fields (e.g. summary) win on merge.
_STREAM_ORDER = ("vector", "bm25")


def search(query, n=5, where=None, use_bm25=True, use_vector=True):
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
        streams["bm25"] = _bm25_stream(query, n, where)

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

    out = []
    for doc_id, score in fused[:n]:
        entry = dict(display.get(doc_id, {}))
        entry["id"] = doc_id
        entry["score"] = round(score, 6)
        out.append(entry)
    return out
