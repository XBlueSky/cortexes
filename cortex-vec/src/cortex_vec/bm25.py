"""Persistent BM25 index over vault notes (one entry per note base path)."""
import pickle
from pathlib import Path

from rank_bm25 import BM25Okapi

from .tokenize import tokenize

# Display/metadata fields carried per doc (everything except the raw body).
_META_FIELDS = ("id", "title", "summary", "tags", "repos", "type", "category")


def _doc_record(doc):
    """Normalize an input doc into the stored record (tokens + metadata)."""
    text = f"{doc.get('title', '')}\n\n{doc.get('body', '')}".strip()
    rec = {f: doc.get(f) for f in _META_FIELDS}
    rec["repos"] = list(doc.get("repos") or [])
    rec["tokens"] = tokenize(text)
    return rec


# Fields this evaluator models, each paired with the predicate that evaluates it.
# ChromaDB accepts any metadata key, so a clause on a key absent here would be
# honoured by the vector stream and ignored by the two that run through
# `_matches` -- one query language per stream again, which is exactly the defect
# the spec below documents. Adding a filter field means adding it here;
# `test_where_shape_lockstep` fails until you do.
#
# The name list and the comparisons are ONE table on purpose. Keeping them apart
# let a field be whitelisted as "known" while no branch ever compared it, which
# passes every record silently -- the same fail-open, one level further in.
_FIELD_MATCHERS = {
    "repo": lambda rec, want: want in rec.get("repos", []),
    "type": lambda rec, want: rec.get("type") == want,
    "category": lambda rec, want: rec.get("category") == want,
}
_KNOWN_FIELDS = frozenset(_FIELD_MATCHERS)


def _matches(rec, where):
    """Evaluate a Chroma-style `where` clause against a stored record.

    Understands exactly the shapes `store._build_where` emits: flat field
    equality plus `$and` / `$or` composition. All three retrieval streams
    (BM25, wikilink graph, and -- via ChromaDB -- vector) must read the same
    query language; a flat-only matcher silently ignored the nested payload
    and dropped the filter entirely. See
    docs/specs/2026-05-27-distill-dedup-repo-filter-blindspot.md.

    The Notes/-are-cross-repo exemption lives in the `$or` branch that
    `_build_where` emits, not in a `type == "note"` special case here.

    Raises ValueError on a clause this evaluator does not model, rather than
    guessing. Silently returning True for an unknown key is how a filter goes
    missing without anyone noticing; the callers wrap this in the same
    degrade-to-empty-stream contract they use for every other failure, so a
    drift fails closed in production and loudly in the tests.
    """
    if not where:
        return True
    if "$and" in where:
        return all(_matches(rec, clause) for clause in where["$and"])
    if "$or" in where:
        return any(_matches(rec, clause) for clause in where["$or"])

    unknown = set(where) - _KNOWN_FIELDS
    if unknown:
        raise ValueError(
            f"_matches cannot evaluate {sorted(unknown)}: the filter producer and "
            f"this evaluator have drifted. Add the field to _KNOWN_FIELDS and "
            f"handle it below."
        )
    for field, expected in where.items():
        if isinstance(expected, dict):
            raise ValueError(
                f"_matches does not implement operator form for {field!r}: "
                f"{expected!r}. ChromaDB would honour it and this stream would not."
            )

    return all(_FIELD_MATCHERS[field](rec, want) for field, want in where.items())


class BM25Index:
    """BM25 index persisted as a pickle of doc records; BM25Okapi rebuilt on load."""

    def __init__(self, dir_path):
        self.dir = Path(dir_path)
        self.docs = []          # list of stored records
        self._bm25 = None       # BM25Okapi, lazily (re)built

    @property
    def _file(self):
        return self.dir / "index.pkl"

    def count(self):
        return len(self.docs)

    def _reindex(self):
        corpus = [d["tokens"] for d in self.docs] or [[""]]
        self._bm25 = BM25Okapi(corpus)

    def build_from_docs(self, docs):
        self.docs = [_doc_record(d) for d in docs]
        self._reindex()

    def upsert(self, doc):
        rec = _doc_record(doc)
        self.docs = [d for d in self.docs if d["id"] != rec["id"]]
        self.docs.append(rec)
        self._reindex()

    def delete(self, base_path):
        before = len(self.docs)
        self.docs = [d for d in self.docs if d["id"] != base_path]
        if len(self.docs) != before:
            self._reindex()
        return before - len(self.docs)

    def save(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self._file, "wb") as f:
            pickle.dump(self.docs, f)

    def load(self):
        if not self._file.exists():
            raise FileNotFoundError(f"BM25 index not found at {self._file}; run rebuild")
        with open(self._file, "rb") as f:
            self.docs = pickle.load(f)
        self._reindex()

    def search(self, query, n=5, where=None, synonym_weight=0.0):
        """Return up to n display dicts, best-first, filtered by `where`.

        If synonym_weight > 0, synonym tokens (from synonyms.synonyms_for) are
        scored separately and added at the given weight, and are also admitted
        to the token-overlap gate so synonym-only matches can surface.
        """
        if not self.docs:
            return []
        if self._bm25 is None:
            self._reindex()
        q_toks = tokenize(query)
        q_tokens = set(q_toks)
        scores = self._bm25.get_scores(q_toks)
        if synonym_weight > 0:
            from .synonyms import synonyms_for
            syn_toks = synonyms_for(q_toks)
            if syn_toks:
                scores = scores + synonym_weight * self._bm25.get_scores(syn_toks)
                q_tokens |= set(syn_toks)
        ranked = sorted(
            zip(self.docs, scores), key=lambda pair: pair[1], reverse=True
        )
        out = []
        for rec, sc in ranked:
            # Relevance gate by token overlap: BM25Okapi IDF can be <= 0 for terms
            # that appear in >= half the corpus (and is degenerate on tiny corpora),
            # which would zero out genuine matches. Token overlap is the reliable match test.
            if not (set(rec["tokens"]) & q_tokens):
                continue
            if not _matches(rec, where):
                continue
            out.append({
                "id": rec["id"],
                "score": float(sc),
                "title": rec.get("title") or "",
                "type": rec.get("type") or "",
                "repo": (rec.get("repos") or [""])[0],
                "category": rec.get("category") or "",
                "tags": rec.get("tags") or "",
                "summary": rec.get("summary") or "",
            })
            if len(out) >= n:
                break
        return out
