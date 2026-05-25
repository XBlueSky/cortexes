import json
from types import SimpleNamespace
from cortex_vec import store, fusion


def test_cmd_search_uses_fusion(monkeypatch, capsys):
    captured = {}

    def fake_search(query, n=5, where=None, use_bm25=True, use_vector=True,
                    rerank=None, graph=None):
        captured["query"] = query
        captured["where"] = where
        captured["use_bm25"] = use_bm25
        return [{"id": "Notes/Nginx/cert-renew.md", "score": 0.42, "title": "Nginx 憑證",
                 "type": "note", "repo": "", "category": "Nginx", "tags": "", "summary": "certbot"}]

    monkeypatch.setattr(fusion, "search", fake_search)
    args = SimpleNamespace(query="nginx 憑證", repo=None, type=None, category=None,
                           n=5, no_bm25=False, no_vector=False)
    store.cmd_search(args)

    out = capsys.readouterr().out.strip()
    entry = json.loads(out)
    assert entry["id"] == "Notes/Nginx/cert-renew.md"
    assert captured["query"] == "nginx 憑證"
    assert captured["use_bm25"] is True


def test_cmd_search_no_bm25_flag(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(fusion, "search",
                        lambda query, n=5, where=None, use_bm25=True, use_vector=True,
                               rerank=None, graph=None:
                        seen.update(use_bm25=use_bm25) or [])
    args = SimpleNamespace(query="x", repo=None, type=None, category=None,
                           n=5, no_bm25=True, no_vector=False)
    store.cmd_search(args)
    assert seen["use_bm25"] is False
