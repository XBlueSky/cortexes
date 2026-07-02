from cortex_vec import synonyms
from cortex_vec.tokenize import tokenize


def test_synonyms_bidirectional():
    res = set(synonyms.synonyms_for(tokenize("perf")))
    assert set(tokenize("performance")) <= res
    res2 = set(synonyms.synonyms_for(tokenize("performance")))
    assert "perf" in res2


def test_synonyms_excludes_originals():
    toks = tokenize("cert")
    res = synonyms.synonyms_for(toks)
    assert "cert" not in res
    assert set(tokenize("certificate")) <= set(res)


def test_synonyms_unknown_token_empty():
    assert synonyms.synonyms_for(tokenize("zzzznotaword")) == []
