from pathlib import Path
from cortex_vec import store


class _FakeCol:
    def query(self, **kwargs):
        return {
            "documents": [["# Nginx\n憑證自動更新 certbot", "OOM killer dmesg"]],
            "metadatas": [[
                {"title": "Nginx 憑證", "type": "note", "repo": "", "category": "Nginx",
                 "tags": "", "source_path": "/vault/Notes/Nginx/cert-renew.md"},
                {"title": "Linux OOM", "type": "note", "repo": "", "category": "Linux",
                 "tags": "", "source_path": "/vault/Notes/Linux/oom.md"},
            ]],
            "distances": [[0.1, 0.4]],
        }


def test_vector_stream_dedup_and_score(monkeypatch):
    monkeypatch.setattr(store, "get_client", lambda: object())
    monkeypatch.setattr(store, "get_collection", lambda client: _FakeCol())
    monkeypatch.setattr(store, "get_vault_path", lambda: Path("/vault"))

    items = store.vector_stream("nginx 憑證", n=5)
    assert items[0]["id"] == "Notes/Nginx/cert-renew.md"
    assert items[0]["score"] == 0.9  # 1 - 0.1
    assert items[1]["id"] == "Notes/Linux/oom.md"
    assert items[0]["title"] == "Nginx 憑證"
