from cortex_vec.eval import adapters


def _docs():
    return [
        {"id": "Notes/Nginx/cert-renew.md", "title": "Nginx 憑證自動更新",
         "body": "certbot nginx TLS certificate renew", "summary": "certbot",
         "tags": "", "repos": [], "type": "note", "category": "Nginx"},
        {"id": "Notes/Linux/oom.md", "title": "Linux OOM",
         "body": "out of memory dmesg killer", "summary": "oom",
         "tags": "", "repos": [], "type": "note", "category": "Linux"},
    ]


def test_grep_adapter_ranks_by_term_overlap():
    a = adapters.GrepAdapter()
    a.init(_docs())
    ranked = a.query("certbot certificate renew", k=5)
    assert ranked[0][0] == "Notes/Nginx/cert-renew.md"
    a.teardown()


def test_bm25_adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters.config, "BM25_DIR", tmp_path / "bm25")
    a = adapters.BM25Adapter()
    a.init(_docs())
    ranked = a.query("oom dmesg", k=5)
    assert ranked[0][0] == "Notes/Linux/oom.md"
    a.teardown()


def test_hybrid_adapter_calls_fusion(monkeypatch):
    monkeypatch.setattr(adapters.fusion, "search",
                        lambda query, n, where=None: [{"id": "Notes/Linux/oom.md", "score": 0.5}])
    a = adapters.HybridAdapter()
    a.init(_docs())
    ranked = a.query("oom", k=5)
    assert ranked[0][0] == "Notes/Linux/oom.md"
    a.teardown()
