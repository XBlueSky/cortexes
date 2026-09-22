"""Lock the BM25 filter to the `where` shapes `_build_where` actually emits.

The earlier repo-filter fix (docs/specs/2026-05-27-distill-dedup-repo-filter-
blindspot.md) changed `_build_where` to emit `{"$or": [...]}` for Chroma but
left BM25's `_matches` doing flat `in` checks. The unit tests of that change
fed `_matches` a flat `{"repo": X}` dict that `_build_where` never produces,
so the real payload sailed through unfiltered. Every test here therefore
builds its `where` through `_build_where` instead of hand-writing one.
"""
import pytest

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


def _clause_keys(where):
    """Every field name reachable in a `where` payload, through $and/$or."""
    if not where:
        return set()
    keys = set()
    for k, v in where.items():
        if k in ("$and", "$or"):
            for clause in v:
                keys |= _clause_keys(clause)
        else:
            keys.add(k)
    return keys


def test_build_where_emits_only_fields_matches_models():
    """Lock the producer's field set to the evaluator's.

    The vector stream hands its clause to ChromaDB, which honours *any*
    metadata key. The BM25 and wikilink-graph streams hand it to `_matches`,
    which models three. A filter field added to `_build_where` and not to
    `_matches` is therefore obeyed by one stream and silently ignored by two —
    the same drift as the original defect, one field later. This test fails the
    moment the two sides diverge, instead of a dedup run failing months later.
    """
    emitted = set()
    for kwargs in ({"repo": "r"}, {"type": "note"}, {"category": "c"},
                   {"repo": "r", "type": "note"}, {"repo": "r", "category": "c"},
                   {"repo": "r", "type": "note", "category": "c"}):
        emitted |= _clause_keys(store._build_where(**kwargs))
    assert emitted, "producer emitted nothing — the sweep above stopped working"
    assert emitted <= set(bm25._KNOWN_FIELDS), (
        f"_build_where emits {sorted(emitted - set(bm25._KNOWN_FIELDS))}, which "
        f"_matches does not model: ChromaDB would filter on it and the BM25 and "
        f"graph streams would not."
    )


def test_matches_refuses_a_field_it_does_not_model():
    """Silence on an unknown key is how a filter goes missing unnoticed."""
    rec = {"id": "x", "type": "project", "category": "c", "repos": ["A"]}
    with pytest.raises(ValueError, match="status"):
        bm25._matches(rec, {"status": "active"})


def test_matches_refuses_operator_form():
    """ChromaDB implements `$in`/`$ne`; this evaluator does not, so it says so.

    Before, an operator clause fell through to `where["repo"] not in rec["repos"]`
    — a dict compared against a list, always False — so the stream quietly
    dropped everything instead of admitting it could not evaluate the clause.
    """
    rec = {"id": "x", "type": "project", "category": "c", "repos": ["A"]}
    with pytest.raises(ValueError, match="operator form"):
        bm25._matches(rec, {"repo": {"$in": ["A"]}})


def test_unknown_clause_degrades_the_stream_rather_than_the_query(tmp_path):
    """Fail-closed in production, fail-loud in tests: both halves of the contract.

    `_matches` raising must not take a user's search down; the stream wrappers
    already degrade to empty on any exception, so an undecidable clause returns
    no keyword hits rather than a traceback.
    """
    from cortex_vec import fusion
    assert fusion._bm25_stream("oauth", 5, {"status": "active"}) == []


def test_known_fields_and_matchers_cannot_drift_apart():
    """A field cannot be declared known without a comparison behind it.

    The first version of this guard kept the name set and the comparisons in
    two places, so a field added to the set but not to the `if` chain was
    declared "modelled" and then matched everything -- the same fail-open the
    guard exists to prevent, one level in. They are one table now; this pins
    that.
    """
    assert set(bm25._KNOWN_FIELDS) == set(bm25._FIELD_MATCHERS)
    rec = {"id": "x", "type": "project", "category": "c", "repos": ["A"]}
    for field in bm25._KNOWN_FIELDS:
        # Every modelled field must be able to REJECT something; a matcher that
        # always returns True is the failure mode being guarded against.
        assert bm25._matches(rec, {field: "\x00definitely-not-a-real-value"}) is False, (
            f"field {field!r} is declared known but its matcher accepts anything"
        )
