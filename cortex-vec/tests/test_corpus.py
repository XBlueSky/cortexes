import json
import pytest
from cortex_vec.eval import corpus


def _write(tmp_path, rows):
    p = tmp_path / "queries.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return p


def test_load_valid(tmp_path):
    p = _write(tmp_path, [
        {"id": "q-001", "query": "nginx 憑證", "gold": ["Notes/Nginx/cert-renew.md"], "type": "single-note"},
        {"id": "q-002", "query": "oom", "gold": ["Notes/Linux/oom.md"], "type": "single-note"},
    ])
    queries = corpus.load_queries(p)
    assert len(queries) == 2
    assert queries[0]["id"] == "q-001"
    assert queries[0]["gold"] == ["Notes/Nginx/cert-renew.md"]


def test_missing_field_raises(tmp_path):
    p = _write(tmp_path, [{"id": "q-001", "query": "x"}])  # no gold
    with pytest.raises(ValueError, match="gold"):
        corpus.load_queries(p)


def test_check_gold_paths_exist(tmp_path):
    existing = {"Notes/Nginx/cert-renew.md"}
    queries = [
        {"id": "q-001", "query": "x", "gold": ["Notes/Nginx/cert-renew.md"], "type": "t"},
        {"id": "q-002", "query": "y", "gold": ["Notes/Gone/missing.md"], "type": "t"},
    ]
    missing = corpus.check_gold_paths(queries, existing)
    assert missing == {"q-002": ["Notes/Gone/missing.md"]}
