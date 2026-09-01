"""Runtime smoke test: /cortexes:query actually resolves and searches a vault.

File-existence and `claude plugin details` inventory checks only prove the
command file ships. They do not prove the slash command resolves under the
renamed `cortexes:` namespace, that it reaches the cortex-query skill now that
the no-op `skills:` frontmatter is gone, or that the skill finds anything. This
drives the real CLI against a synthetic vault and checks the answer.

Opt-in: needs an authenticated `claude` (credentials live under the default
config dir, so the run cannot be sandboxed into a throwaway HOME) and spends
tokens, which CI has neither. Enable with:

    CORTEX_RUNTIME_SMOKE=1 pytest tests/test_query_command_smoke.py

The test writes ~/.cortex/config.json because cortex_vec.config derives it from
Path.home() with no env override. It refuses to run if that path already
exists, and removes what it created afterwards.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SENTINEL = "ZORBLAX-SENTINEL-7719"

pytestmark = pytest.mark.skipif(
    os.environ.get("CORTEX_RUNTIME_SMOKE") != "1" or shutil.which("claude") is None,
    reason="runtime smoke test: set CORTEX_RUNTIME_SMOKE=1 and have an authenticated `claude`",
)


def _vault(tmp_path):
    vault = tmp_path / "vault"
    (vault / "Notes" / "Nginx").mkdir(parents=True)
    (vault / "Projects" / "demo").mkdir(parents=True)
    (vault / "Raw").mkdir(parents=True)
    (vault / "Notes" / "Nginx" / "ssl-renewal.md").write_text(
        "---\ntitle: SSL renewal runbook\ntags: [nginx, tls]\n---\n"
        "# SSL certificate renewal\n\n"
        f"The renewal job is guarded by the sentinel token {SENTINEL}.\n"
        "Always run `nginx -t` before `nginx -s reload`.\n"
    )
    # Decoy: a hit on this would mean the search is not actually discriminating.
    (vault / "Notes" / "Nginx" / "unrelated.md").write_text(
        "---\ntitle: Unrelated note\n---\nNothing to do with certificates.\n"
    )
    return vault


@pytest.fixture
def cortex_config(tmp_path):
    """Point ~/.cortex/config.json at a synthetic vault, then restore."""
    cfg_dir = Path.home() / ".cortex"
    if cfg_dir.exists():
        pytest.skip(f"{cfg_dir} already exists — refusing to touch a real config")
    vault = _vault(tmp_path)
    cfg_dir.mkdir(parents=True)
    try:
        (cfg_dir / "config.json").write_text(json.dumps({
            "vault_path": str(vault),
            "author": "smoke test",
            "author_email": "smoke@example.com",
            "git": {"auto_commit": False, "auto_push": False},
        }))
        yield vault
    finally:
        shutil.rmtree(cfg_dir, ignore_errors=True)


def _claude(prompt):
    env = {**os.environ, "CORTEX_SKIP_RECORD": "1"}
    return subprocess.run(
        ["claude", "-p", prompt, "--plugin-dir", str(REPO_ROOT)],
        capture_output=True, text=True, env=env, timeout=600,
    )


def test_query_command_searches_the_vault(cortex_config):
    r = _claude(f"/cortexes:query {SENTINEL}")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    # It resolved, reached the skill, resolved the vault, and found the page.
    assert "ssl-renewal" in out, out
    # And it discriminated: the decoy note is not a hit.
    assert "unrelated" not in out.lower(), out


def test_old_namespace_does_not_resolve(cortex_config):
    r = _claude(f"/cortex:query {SENTINEL}")
    assert "Unknown command: /cortex:query" in r.stdout + r.stderr, r.stdout
