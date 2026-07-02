"""Static synonym groups (common zh/en tech terms).

Groups are written in human-readable form; at first use each term is run
through the same tokenizer as the index/query, so the synonym lookup lives in
the SAME token space as BM25 (lowercased, stemmed, jieba-segmented).
"""
from .tokenize import tokenize

SYNONYM_GROUPS = [
    ["套件", "package"],
    ["憑證", "certificate", "cert", "tls", "ssl"],
    ["週報", "weekly report"],
    ["登入", "login", "signin", "authentication", "auth"],
    ["記憶體", "memory", "ram"],
    ["效能", "performance", "perf"],
    ["編譯", "build", "compile"],
    ["測試", "test", "unittest"],
    ["設定", "config", "configuration", "設定檔"],
]

_index = None  # token -> set of synonym tokens (built lazily)


def _build_index():
    global _index
    _index = {}
    for group in SYNONYM_GROUPS:
        group_tokens = set()
        for term in group:
            group_tokens.update(tokenize(term))
        for tok in group_tokens:
            _index.setdefault(tok, set()).update(group_tokens - {tok})


def synonyms_for(tokens):
    """Return extra synonym tokens for the given query tokens (sorted, originals excluded)."""
    if _index is None:
        _build_index()
    originals = set(tokens)
    extra = set()
    for tok in originals:
        extra.update(_index.get(tok, set()))
    return sorted(extra - originals)
