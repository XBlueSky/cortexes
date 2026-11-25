"""An index used through the `http` embedding type, end to end.

Real chroma under tmp_path. The endpoint is `embedding_endpoint` (conftest):
documents and queries are embedded in-process and nothing leaves the test.
The block has no `base_url`, so the URL comes from OPENAI_BASE_URL, which
conftest points at a closed local port.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from cortex_vec import cli, config, fusion, store
from cortex_vec.http_embedding import EmbeddingEndpointError

KEY = "k-test-123"
URL = "http://127.0.0.1:9/v1/embeddings"


@pytest.fixture
def vault(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    (root / "Notes").mkdir(parents=True)
    models = {"embedding": {"type": "http", "model": "my-embedding-model",
                            "api_key_env": "MY_EMBED_KEY"}}
    monkeypatch.setattr(config, "load_config", lambda: {"models": models, "vault_path": str(root)})
    monkeypatch.setenv("MY_EMBED_KEY", KEY)
    return root


def _by_topic(request):
    texts = json.loads(request.content)["input"]
    return httpx.Response(200, json={"embedding": [
        [1.0, 0.0, 0.0] if "nginx" in text else [0.0, 1.0, 0.0] for text in texts]})


def test_importing_the_store_registers_cortex_http():
    # In a fresh interpreter: `status` and `delete` open the index without ever
    # building the function, and chroma looks the recorded name up in its registry.
    code = ("import cortex_vec.store\n"
            "from chromadb.utils.embedding_functions import known_embedding_functions as known\n"
            "print(known['cortex-http'].__name__)")
    # The environment is passed inline, not kept in a local: a failing assert
    # must never be able to print it.
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(Path(store.__file__).parents[1])})
    assert done.stdout.strip() == "HttpEmbeddingFunction", done.stderr[-300:]


def test_upsert_then_search_through_the_endpoint(vault, monkeypatch, embedding_endpoint):
    (vault / "Notes" / "nginx.md").write_text(
        "---\ntitle: nginx cert renewal\n---\ncertbot renews it\n", encoding="utf-8")
    (vault / "Notes" / "oom.md").write_text(
        "---\ntitle: OOM killer\n---\ndmesg shows out of memory\n", encoding="utf-8")
    monkeypatch.setattr(store, "_generate_summary", lambda title, tags, body: f"{title} summary")
    seen = embedding_endpoint(_by_topic)
    for name in ("nginx", "oom"):
        monkeypatch.setattr(sys, "argv", ["cortex-vec", "upsert", f"Notes/{name}.md"])
        cli.main()
    assert len(seen.requests) == 4                           # body + summary for each note
    assert {(str(r.url), r.headers["authorization"]) for r in seen.requests} == {
        (URL, f"Bearer {KEY}")}
    assert {json.loads(r.content)["model"] for r in seen.requests} == {"my-embedding-model"}
    assert json.loads((store.VECTORSTORE_DIR / store.SIGNATURE_FILE).read_text()) == {
        "type": "http", "model": "my-embedding-model"}
    notes = []
    hits = fusion._vector_stream("renew the nginx certificate", 5, None, notes)
    assert hits[0]["id"] == "Notes/nginx.md" and hits[0]["score"] == pytest.approx(1.0)
    assert notes == []


def test_a_failing_endpoint_leaves_search_on_bm25_with_a_one_line_note(vault, embedding_endpoint):
    embedding_endpoint(lambda r: httpx.Response(503, text=f"<html>\nupstream said {KEY}\n</html>"))
    notes = []
    assert fusion._vector_stream("anything", 5, None, notes) == []
    assert notes[0].startswith(
        "vector stream failed (EmbeddingEndpointError: embedding endpoint returned HTTP 503")
    assert notes[0].endswith("results are BM25-only")
    assert "\n" not in notes[0] and KEY not in notes[0]


def test_the_endpoint_error_keeps_its_type_through_chroma(vault, embedding_endpoint):
    # chroma rewrites the message in place and re-raises the same object.
    embedding_endpoint(lambda r: httpx.Response(401, json={"error": "nope"}))
    col = store.get_collection(store.get_client())
    with pytest.raises(EmbeddingEndpointError, match="HTTP 401"):
        col.upsert(ids=["Notes/a.md"], documents=["text"])
