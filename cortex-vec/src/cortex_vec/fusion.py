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
