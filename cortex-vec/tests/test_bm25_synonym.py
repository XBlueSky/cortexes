from cortex_vec import bm25


def _docs():
    return [
        {"id": "Notes/A/auth.md", "title": "登入設定",
         "body": "signin authentication 設定教學", "summary": "auth",
         "tags": "", "repos": [], "type": "note", "category": "A"},
        {"id": "Notes/B/cert.md", "title": "憑證更新",
         "body": "certificate renew 教學", "summary": "cert",
         "tags": "", "repos": [], "type": "note", "category": "B"},
    ]


def test_synonym_weight_surfaces_synonym_only_match(tmp_path):
    idx = bm25.BM25Index(tmp_path / "bm25")
    idx.build_from_docs(_docs())
    withsyn = [h["id"] for h in idx.search("login", n=5, synonym_weight=0.7)]
    assert "Notes/A/auth.md" in withsyn
    syn_hits = [h["id"] for h in idx.search("cert", n=5, synonym_weight=0.7)]
    assert "Notes/B/cert.md" in syn_hits


def test_synonym_weight_zero_is_plain(tmp_path):
    idx = bm25.BM25Index(tmp_path / "bm25")
    idx.build_from_docs(_docs())
    a = idx.search("certificate", n=5, synonym_weight=0.0)
    b = idx.search("certificate", n=5)
    assert [h["id"] for h in a] == [h["id"] for h in b]
