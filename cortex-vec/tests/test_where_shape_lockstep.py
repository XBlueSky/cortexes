"""Lock the BM25 filter to the `where` shapes `_build_where` actually emits.

The earlier repo-filter fix (docs/specs/2026-05-27-distill-dedup-repo-filter-
blindspot.md) changed `_build_where` to emit `{"$or": [...]}` for Chroma but
left BM25's `_matches` doing flat `in` checks. The unit tests of that change
fed `_matches` a flat `{"repo": X}` dict that `_build_where` never produces,
so the real payload sailed through unfiltered. Every test here therefore
builds its `where` through `_build_where` instead of hand-writing one.
"""
from cortex_vec import bm25, store


def _docs():
    return [
        {"id": "Notes/Nginx/cert-renew.md", "title": "Nginx 憑證自動更新",
         "body": "用 certbot 設定 nginx TLS certificate 自動 renew", "summary": "certbot renew",
         "tags": "", "repos": [], "type": "note", "category": "Nginx"},
        {"id": "Notes/Nginx/oauth-notes.md", "title": "Nginx OAuth 筆記",
         "body": "oauth token refresh 在 Nginx 的通則", "summary": "oauth",
         "tags": "", "repos": [], "type": "note", "category": "Nginx"},
        {"id": "Projects/acme-core/oauth.md", "title": "acme-core OAuth",
         "body": "token refresh oauth", "summary": "oauth",
         "tags": "", "repos": ["acme-core"], "type": "project", "category": "acme-core"},
        {"id": "Projects/acme-web/oauth-token.md", "title": "acme-web oauth token",
         "body": "oauth token refresh in acme-web", "summary": "oauth token",
         "tags": "", "repos": ["acme-web"], "type": "project", "category": "acme-web"},
    ]


def _index(tmp_path):
    idx = bm25.BM25Index(tmp_path / "bm25")
    idx.build_from_docs(_docs())
    return idx


def test_build_where_repo_shape_narrows_projects(tmp_path):
    """--repo must exclude out-of-repo Projects/ pages from the BM25 stream."""
    where = store._build_where(repo="acme-core")
    hits = _index(tmp_path).search("oauth token refresh", n=5, where=where)
    ids = [h["id"] for h in hits]
    assert "Projects/acme-web/oauth-token.md" not in ids, (
        f"out-of-repo Project leaked through the real where shape: {ids}"
    )
    assert "Projects/acme-core/oauth.md" in ids


def test_build_where_repo_shape_keeps_cross_repo_notes(tmp_path):
    """Notes/ stay cross-repo: the $or branch exempts them from the repo clause."""
    where = store._build_where(repo="acme-core")
    hits = _index(tmp_path).search("oauth token refresh", n=5, where=where)
    assert "Notes/Nginx/oauth-notes.md" in [h["id"] for h in hits]


def test_build_where_repo_and_category_still_applies_category(tmp_path):
    """--repo combined with --category must not disable the category clause.

    `_build_where` nests both under `$and`; a flat matcher sees neither key.
    """
    where = store._build_where(repo="acme-core", category="Nginx")
    hits = _index(tmp_path).search("oauth token refresh", n=5, where=where)
    ids = [h["id"] for h in hits]
    assert all(h["category"] == "Nginx" for h in hits), (
        f"category clause ignored under the $and shape: {ids}"
    )


def test_build_where_repo_and_type_still_applies_type(tmp_path):
    """--repo combined with --type must not disable the type clause."""
    where = store._build_where(repo="acme-core", type="project")
    hits = _index(tmp_path).search("oauth token refresh", n=5, where=where)
    assert all(h["type"] == "project" for h in hits), (
        f"type clause ignored under the $and shape: {[h['id'] for h in hits]}"
    )


def test_matches_evaluates_nested_or(tmp_path):
    """_matches understands $or directly, not just as a side effect of search."""
    note = {"id": "Notes/Nginx/x.md", "type": "note", "category": "Nginx", "repos": []}
    other = {"id": "Projects/acme-web/x.md", "type": "project",
             "category": "acme-web", "repos": ["acme-web"]}
    where = {"$or": [{"repo": "acme-core"}, {"type": "note"}]}
    assert bm25._matches(note, where) is True
    assert bm25._matches(other, where) is False


def test_matches_evaluates_nested_and(tmp_path):
    """_matches understands $and: every sub-clause must hold."""
    mine = {"id": "Projects/acme-core/x.md", "type": "project",
            "category": "acme-core", "repos": ["acme-core"]}
    where = {"$and": [{"$or": [{"repo": "acme-core"}, {"type": "note"}]},
                      {"category": "Nginx"}]}
    assert bm25._matches(mine, where) is False
