"""CJK-aware tokenizer for BM25.

Splits Han runs with jieba (soft-falls to whole-run if jieba missing),
stems Latin words with a Porter stemmer, and preserves Latin word
boundaries embedded inside CJK text (e.g. "機器學習ML技術").
"""
import re
import sys

# Han, Hiragana/Katakana, Hangul ranges. cortex content is zh+en; non-Han CJK
# runs are kept whole (jieba targets Han).
CJK_RUN_RE = re.compile(r"[㐀-鿿぀-ヿ가-힯]+")
HAN_RE = re.compile(r"[㐀-鿿]")
# Keep alphanumerics, CJK, and path-ish chars; everything else -> space.
_CLEAN_RE = re.compile(r"[^\w\s/.\\\-㐀-鿿぀-ヿ가-힯]", re.UNICODE)

_stemmer = None
_jieba_ok = None


def _stem(word):
    global _stemmer
    if _stemmer is None:
        import snowballstemmer
        _stemmer = snowballstemmer.stemmer("porter")
    return _stemmer.stemWord(word)


def _seg_han(run):
    global _jieba_ok
    if _jieba_ok is None:
        try:
            import jieba  # noqa: F401
            _jieba_ok = True
        except Exception:
            _jieba_ok = False
            print("cortex-vec: jieba not installed; CJK runs kept whole "
                  "(install jieba for word-level CJK recall)", file=sys.stderr)
    if not _jieba_ok:
        return [run]
    import jieba
    return [w for w in jieba.lcut(run, HMM=True) if w.strip()]


def _segment_token(token):
    """Split one whitespace-delimited token that contains CJK into parts,
    preserving embedded Latin runs."""
    parts = []
    cursor = 0
    for m in CJK_RUN_RE.finditer(token):
        if m.start() > cursor:
            latin = token[cursor:m.start()].strip()
            if latin:
                parts.append(_stem(latin))
        run = m.group()
        if HAN_RE.search(run):
            parts.extend(_seg_han(run))
        else:
            parts.append(run)
        cursor = m.end()
    if cursor < len(token):
        latin = token[cursor:].strip()
        if latin:
            parts.append(_stem(latin))
    return parts


def tokenize(text):
    """Return a list of lowercased tokens for BM25 indexing/querying."""
    cleaned = _CLEAN_RE.sub(" ", text.lower())
    out = []
    for raw in cleaned.split():
        if not raw:
            continue
        if CJK_RUN_RE.search(raw):
            out.extend(t for t in _segment_token(raw) if t)
        else:
            out.append(_stem(raw))
    return out
