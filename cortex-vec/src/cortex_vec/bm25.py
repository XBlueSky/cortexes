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


def _matches(rec, where):
    if not where:
        return True
    if "repo" in where and where["repo"] not in rec.get("repos", []):
        return False
    if "type" in where and rec.get("type") != where["type"]:
        return False
    if "category" in where and rec.get("category") != where["category"]:
        return False
    return True


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

    def search(self, query, n=5, where=None):
        """Return up to n display dicts, best-first, filtered by `where`."""
        if not self.docs:
            return []
        if self._bm25 is None:
            self._reindex()
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(
            zip(self.docs, scores), key=lambda pair: pair[1], reverse=True
        )
        out = []
        for rec, sc in ranked:
            if sc <= 0:
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
