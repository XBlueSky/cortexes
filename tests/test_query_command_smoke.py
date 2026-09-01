"""Runtime smoke test: /cortexes:query actually resolves and searches a vault.

File-existence and `claude plugin details` inventory checks only prove the
command file ships. They do not prove the slash command resolves under the
renamed `cortexes:` namespace, that it reaches the cortex-query skill now that
the no-op `skills:` frontmatter is gone, or that the skill finds anything.
This drives the real CLI against a synthetic vault and checks the answer.

Isolation is by `CORTEX_VAULT_PATH`, the documented override that the hooks,
`cortex_vec.config.get_vault_path()`, and the cortex-query skill all honour.
Nothing under $HOME is created, moved, or deleted — in particular this test
never touches ~/.cortex, which may hold a real vault configuration.

Opt-in: needs an authenticated `claude` (credentials live under the default
config dir, so the run cannot be sandboxed into a throwaway HOME) and spends
tokens, which CI has neither. Enable with:

    CORTEX_RUNTIME_SMOKE=1 pytest tests/test_query_command_smoke.py
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Distinct tokens: one the search must find, one it must not surface. A shared
# or generic decoy string ("unrelated") could match incidental prose in the
# model's own explanation and pass a negative assertion by accident.
HIT_SENTINEL = "ZORBLAX-SENTINEL-7719"
DECOY_SENTINEL = "QUOXBAR-DECOY-4402"

pytestmark = pytest.mark.skipif(
    os.environ.get("CORTEX_RUNTIME_SMOKE") != "1" or shutil.which("claude") is None,
    reason="runtime smoke test: set CORTEX_RUNTIME_SMOKE=1 and have an authenticated `claude`",
)


@pytest.fixture
def synthetic_vault(tmp_path):
    """A throwaway vault under tmp_path. Nothing outside tmp_path is touched."""
    vault = tmp_path / "vault"
    (vault / "Notes" / "Nginx").mkdir(parents=True)
    (vault / "Projects" / "demo").mkdir(parents=True)
    (vault / "Raw").mkdir(parents=True)
    (vault / "Notes" / "Nginx" / "ssl-renewal.md").write_text(
        "---\ntitle: SSL renewal runbook\ntags: [nginx, tls]\n---\n"
        "# SSL certificate renewal\n\n"
        f"The renewal job is guarded by the sentinel token {HIT_SENTINEL}.\n"
        "Always run `nginx -t` before `nginx -s reload`.\n"
    )
    # A hit on this would mean the search is not discriminating.
    (vault / "Notes" / "Nginx" / "unrelated.md").write_text(
        "---\ntitle: Unrelated note\n---\n"
        f"Nothing to do with certificates. Decoy token {DECOY_SENTINEL}.\n"
    )
    return vault


def _claude(prompt, vault):
    env = {**os.environ}
    env["CORTEX_VAULT_PATH"] = str(vault)   # the documented override
    env["CORTEX_SKIP_RECORD"] = "1"         # no Raw/ write from this session
    env["CORTEX_NO_CLASSIFIER"] = "1"       # no nested classifier calls
    env.pop("OPENAI_API_KEY", None)         # nothing reaches OpenAI from here
    # --add-dir: the vault sits outside the session's working directory, and
    # file/Bash access is confined to the workspace. Now that the command
    # scopes Bash instead of pre-approving all of it, that boundary applies —
    # this is the same grant a real user with an out-of-workspace vault needs
    # for the grep fallback layer.
    return subprocess.run(
        ["claude", "-p", prompt,
         "--plugin-dir", str(REPO_ROOT), "--add-dir", str(vault)],
        capture_output=True, text=True, env=env, timeout=600,
    )


def test_query_command_searches_the_vault(synthetic_vault):
    r = _claude(f"/cortexes:query {HIT_SENTINEL}", synthetic_vault)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    # It resolved, reached the skill, resolved the vault, and found the page.
    assert "ssl-renewal" in out, out
    # And it discriminated: the decoy note is not a hit.
    assert DECOY_SENTINEL not in out, out


def test_old_namespace_does_not_resolve(synthetic_vault):
    r = _claude(f"/cortex:query {HIT_SENTINEL}", synthetic_vault)
    assert "Unknown command: /cortex:query" in r.stdout + r.stderr, r.stdout
