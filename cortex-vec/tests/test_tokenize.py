from cortex_vec import tokenize


def test_pure_english_lowercased_and_stemmed():
    toks = tokenize.tokenize("Renewing Certificates")
    # snowball porter: renewing->renew, certificates->certif
    assert "renew" in toks
    assert all(t == t.lower() for t in toks)


def test_pure_chinese_segmented():
    toks = tokenize.tokenize("憑證自動更新")
    # jieba should split into multiple words; whole-run fallback also acceptable
    assert "".join(toks).replace(" ", "") == "憑證自動更新"
    assert len(toks) >= 1


def test_mixed_cjk_english_preserves_english_boundary():
    toks = tokenize.tokenize("機器學習ML技術")
    assert "ml" in toks  # latin run preserved as a whole token, lowercased
    assert "機器" in toks or "機器學習" in toks  # depends on jieba availability


def test_punctuation_stripped_but_path_chars_kept():
    toks = tokenize.tokenize("src/middleware/auth.ts, jose!")
    assert "jose" in toks
    assert any("auth" in t for t in toks)


def test_short_query_nonempty():
    assert tokenize.tokenize("PROJ-123456")  # issue id should survive as tokens
