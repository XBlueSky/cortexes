from cortex_vec import bm25


def _docs():
    return [
        {"id": "Notes/Nginx/cert-renew.md", "title": "Nginx 憑證自動更新",
         "body": "用 certbot 設定 nginx TLS certificate 自動 renew", "summary": "certbot renew",
         "tags": "", "repos": [], "type": "note", "category": "Nginx"},
        {"id": "Notes/Linux/oom.md", "title": "Linux OOM",
         "body": "out of memory killer dmesg", "summary": "oom",
         "tags": "", "repos": [], "type": "note", "category": "Linux"},
        {"id": "Projects/libsynow3/oauth.md", "title": "libsynow3 OAuth",
         "body": "token refresh oauth", "summary": "oauth",
         "tags": "", "repos": ["libsynow3"], "type": "project", "category": "libsynow3"},
    ]


def test_build_and_search_finds_relevant(tmp_path):
    idx = bm25.BM25Index(tmp_path / "bm25")
    idx.build_from_docs(_docs())
    hits = idx.search("nginx certificate renew", n=3)
    assert hits[0]["id"] == "Notes/Nginx/cert-renew.md"
    assert hits[0]["title"] == "Nginx 憑證自動更新"


def test_search_with_repo_filter(tmp_path):
    idx = bm25.BM25Index(tmp_path / "bm25")
    idx.build_from_docs(_docs())
    hits = idx.search("oauth token", n=5, where={"repo": "libsynow3"})
    assert all(h["id"].startswith("Projects/libsynow3/") for h in hits)
    assert hits and hits[0]["id"] == "Projects/libsynow3/oauth.md"


def test_persist_and_load_roundtrip(tmp_path):
    idx = bm25.BM25Index(tmp_path / "bm25")
    idx.build_from_docs(_docs())
    idx.save()
    idx2 = bm25.BM25Index(tmp_path / "bm25")
    idx2.load()
    assert idx2.count() == 3
    hits = idx2.search("oom dmesg", n=2)
    assert hits[0]["id"] == "Notes/Linux/oom.md"


def test_upsert_and_delete(tmp_path):
    idx = bm25.BM25Index(tmp_path / "bm25")
    idx.build_from_docs(_docs())
    idx.upsert({"id": "Notes/New/x.md", "title": "brand new redis cache note",
                "body": "redis cache eviction", "summary": "redis",
                "tags": "", "repos": [], "type": "note", "category": "New"})
    assert idx.count() == 4
    assert idx.search("redis cache", n=1)[0]["id"] == "Notes/New/x.md"
    idx.delete("Notes/New/x.md")
    assert idx.count() == 3


def test_search_with_repo_filter_includes_cross_repo_notes(tmp_path):
    """--repo X must surface relevant Notes/ entries regardless of their
    repos field. Notes/ pages are cross-repo by design and must never be
    excluded by the repo filter; the filter only narrows Projects/.
    """
    idx = bm25.BM25Index(tmp_path / "bm25")
    idx.build_from_docs(_docs())
    # Query matches the Notes/Nginx page; --repo filter mentions a different
    # repo (libsynow3). The Notes/ entry must still appear.
    hits = idx.search("nginx certificate renew", n=5,
                      where={"repo": "libsynow3"})
    assert any(h["id"] == "Notes/Nginx/cert-renew.md" for h in hits), (
        f"Notes/Nginx note missing under --repo libsynow3; got {[h['id'] for h in hits]}"
    )


def test_search_with_repo_filter_still_narrows_projects(tmp_path):
    """--repo X still excludes Projects/ pages whose repos don't match.

    Regression guard: the fix widens for type=note only; Project/ pages
    from a different repo must still be filtered out.
    """
    idx = bm25.BM25Index(tmp_path / "bm25")
    # Add a Project page in a different repo than libsynow3.
    docs = _docs() + [{
        "id": "Projects/syno-nextweb/oauth-token.md",
        "title": "syno-nextweb oauth token",
        "body": "oauth token refresh in syno-nextweb",
        "summary": "oauth token",
        "tags": "",
        "repos": ["syno-nextweb"],
        "type": "project",
        "category": "syno-nextweb",
    }]
    idx.build_from_docs(docs)
    hits = idx.search("oauth token refresh", n=5,
                      where={"repo": "libsynow3"})
    ids = [h["id"] for h in hits]
    assert "Projects/syno-nextweb/oauth-token.md" not in ids, (
        f"Project page from wrong repo leaked through filter: got {ids}"
    )
