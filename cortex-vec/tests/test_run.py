from cortex_vec.eval import run


class _FakeAdapter:
    name = "fake"

    def __init__(self, ranking):
        self._r = ranking

    def init(self, docs):
        pass

    def query(self, q, k):
        return self._r

    def teardown(self):
        pass


def test_run_adapters_produces_rows():
    queries = [
        {"id": "q1", "query": "nginx", "gold": ["Notes/Nginx/cert-renew.md"], "type": "single-note"},
        {"id": "q2", "query": "oom", "gold": ["Notes/Linux/oom.md"], "type": "single-note"},
    ]
    adapter = _FakeAdapter([("Notes/Nginx/cert-renew.md", 1.0), ("Notes/Linux/oom.md", 0.5)])
    rows = run.run_adapter(adapter, queries, k=5)
    assert len(rows) == 2
    assert rows[0]["adapter"] == "fake"
    assert rows[0]["hit"] is True              # q1 gold at rank 1
    assert rows[0]["reciprocal_rank"] == 1.0
    assert rows[1]["reciprocal_rank"] == 0.5   # q2 gold at rank 2
    assert "latency_ms" in rows[0]
