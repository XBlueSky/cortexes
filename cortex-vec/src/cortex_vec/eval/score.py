"""Retrieval metrics: P@k, R@k, MRR, hit, and aggregation."""
from statistics import median


def score_query(ranked, gold, k):
    """Score one query's ranked base-path list against a gold set.

    ranked: list[str] of base paths, best-first.
    gold:   set[str] of relevant base paths.
    Returns dict with precision_at_k, recall_at_k, reciprocal_rank, hit.
    """
    gold = set(gold)
    top_k = ranked[:k]
    hits = sum(1 for p in top_k if p in gold)
    precision = hits / k if k else 0.0
    recall = hits / len(gold) if gold else 0.0

    reciprocal_rank = 0.0
    for idx, p in enumerate(top_k):
        if p in gold:
            reciprocal_rank = 1.0 / (idx + 1)
            break

    return {
        "precision_at_k": precision,
        "recall_at_k": recall,
        "reciprocal_rank": reciprocal_rank,
        "hit": hits > 0,
    }


def aggregate(rows):
    """Aggregate per-query score rows into by_adapter and by_type summaries.

    Each row must have: adapter, type, precision_at_k, recall_at_k,
    reciprocal_rank, hit, latency_ms.
    """
    by_adapter = {}
    by_type = {}

    def _bucket(d, key):
        return d.setdefault(key, [])

    for row in rows:
        _bucket(by_adapter, row["adapter"]).append(row)
        _bucket(by_type, (row["adapter"], row["type"])).append(row)

    def _summary(group):
        n = len(group)
        return {
            "n": n,
            "p": sum(g["precision_at_k"] for g in group) / n,
            "r": sum(g["recall_at_k"] for g in group) / n,
            "mrr": sum(g["reciprocal_rank"] for g in group) / n,
            "hit_rate": sum(1 for g in group if g["hit"]) / n,
            "latency_p50": median(g["latency_ms"] for g in group),
        }

    return {
        "by_adapter": {a: _summary(g) for a, g in by_adapter.items()},
        "by_type": {f"{a}/{t}": _summary(g) for (a, t), g in by_type.items()},
    }
