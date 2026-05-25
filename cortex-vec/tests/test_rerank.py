import openai
from cortex_vec import rerank


class _FakeResp:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})})]


class _FakeClient:
    def __init__(self, content):
        self._content = content
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, **kwargs):
        return _FakeResp(self._content)


def _results():
    return [{"id": "a", "title": "A", "summary": ""}, {"id": "b", "title": "B", "summary": ""}]


def test_rerank_reorders_by_llm(monkeypatch):
    monkeypatch.setattr(openai, "OpenAI",
                        lambda: _FakeClient('[{"index": 1, "score": 9}, {"index": 0, "score": 2}]'))
    out = rerank.rerank("q", _results(), model="m", window=15)
    assert [r["id"] for r in out] == ["b", "a"]


def test_rerank_failure_returns_unchanged(monkeypatch):
    def _boom():
        raise RuntimeError("no key")
    monkeypatch.setattr(openai, "OpenAI", _boom)
    res = _results()
    assert rerank.rerank("q", res, model="m", window=15) == res


def test_rerank_empty_results():
    assert rerank.rerank("q", [], model="m", window=15) == []


def test_rerank_handles_fenced_json(monkeypatch):
    fenced = "```json\n[{\"index\": 1, \"score\": 9}, {\"index\": 0, \"score\": 1}]\n```"
    monkeypatch.setattr(openai, "OpenAI", lambda: _FakeClient(fenced))
    out = rerank.rerank("q", _results(), model="m", window=15)
    assert [r["id"] for r in out] == ["b", "a"]
