"""Pluggable retrieval adapters for eval: grep / vector / bm25 / hybrid.

Each adapter exposes init(docs) / query(q, k) -> [(base_path, score)] / teardown().
`docs` is a list of dicts with id/title/body/summary/tags/repos/type/category.
"""
from .. import bm25, config, fusion, store
from ..tokenize import tokenize


class GrepAdapter:
    """Zero-dependency keyword baseline: rank by query-term frequency in title+body."""
    name = "grep"

    def init(self, docs):
        self._docs = [(d["id"], tokenize(f"{d.get('title','')}\n{d.get('body','')}")) for d in docs]

    def query(self, q, k):
        terms = set(tokenize(q))
        scored = []
        for doc_id, toks in self._docs:
            score = sum(1 for t in toks if t in terms)
            if score > 0:
                scored.append((doc_id, float(score)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def teardown(self):
        self._docs = []


class BM25Adapter:
    """Isolated BM25 index over the corpus docs."""
    name = "bm25"

    def init(self, docs):
        self._idx = bm25.BM25Index(config.BM25_DIR.parent / "bm25_eval")
        self._idx.build_from_docs(docs)

    def query(self, q, k):
        return [(h["id"], h["score"]) for h in self._idx.search(q, n=k)]

    def teardown(self):
        self._idx = None


class VectorAdapter:
    """Production vector stream (ChromaDB + OpenAI). Requires a built index.

    init() is a no-op: it queries the live vector store the same way production does.
    Use only against a vault whose vector index is already built.
    """
    name = "vector"

    def init(self, docs):
        pass

    def query(self, q, k):
        return [(it["id"], it["score"]) for it in store.vector_stream(q, k)]

    def teardown(self):
        pass


class HybridAdapter:
    """Full production fusion.search (vector + BM25, RRF)."""
    name = "hybrid"

    def init(self, docs):
        pass

    def query(self, q, k):
        return [(it["id"], it["score"]) for it in fusion.search(q, n=k)]

    def teardown(self):
        pass


REGISTRY = {
    "grep": GrepAdapter,
    "bm25": BM25Adapter,
    "vector": VectorAdapter,
    "hybrid": HybridAdapter,
}
