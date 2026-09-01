"""Runtime smoke test: `/cortexes:query` resolves and reaches its skill.

File-existence and `claude plugin details` inventory checks only prove the
command file ships. They do not prove the slash command resolves under the
renamed `cortexes:` namespace, or that it reaches the cortex-query skill now
that the no-op `skills:` frontmatter is gone. This drives the real CLI.

Scope, and why it is what it is:

`cortex-query` resolves the vault from `~/.cortex/config.json` and nothing
else — `CORTEX_VAULT_PATH` is honoured only by the two SessionStart-side
shell hooks (see the README's env-var table). There is therefore no way to
point the skill at a synthetic vault without writing under `$HOME`, and
writing there is not acceptable: `~/.cortex` may hold a real configuration.
So this test does not assert on retrieved content. It asserts the two things
it *can* prove hermetically — the command resolves to this plugin's skill,
and the old namespace does not — and it **skips entirely** when a real
`~/.cortex/config.json` exists rather than searching someone's own vault and
pulling their note titles into a test session.

Retrieval behaviour itself is covered by the `cortex-vec` unit suite, which
does not need a live model.

Two things keep the run off the machine's real state:
  - a stub `cortex-vec` first on `PATH` that always fails, so no installed
    copy can be invoked and no real BM25/Chroma index under `~/.cortex` can
    be read, whatever the developer happens to have installed;
  - a scrubbed environment: no `OPENAI_API_KEY`, no `CORTEX_*` inherited.

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
REAL_CONFIG = Path.home() / ".cortex" / "config.json"

SENTINEL = "ZORBLAX-SENTINEL-7719"

# Anything the plugin reads from the environment is dropped, so a developer's
# own settings cannot change what the run does.
_SCRUBBED = (
    "OPENAI_API_KEY",
    "CORTEX_VAULT_PATH", "CORTEX_CONFIG", "CORTEX_DIR",
    "CORTEX_SESSION_RECORDING",
)

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("CORTEX_RUNTIME_SMOKE") != "1" or shutil.which("claude") is None,
        reason="runtime smoke test: set CORTEX_RUNTIME_SMOKE=1 and have an authenticated `claude`",
    ),
    pytest.mark.skipif(
        REAL_CONFIG.exists(),
        reason=(
            "~/.cortex/config.json exists — the skill resolves the vault from it and "
            "cannot be redirected, so running would search a real vault. Skipped "
            "rather than isolated by writing under $HOME."
        ),
    ),
]


@pytest.fixture
def stub_bin(tmp_path):
    """A `cortex-vec` on PATH that always fails.

    Without this the test would run whatever `cortex-vec` the developer has
    installed — a published PyPI build rather than this branch — and that
    build would read the real `~/.cortex/bm25` index.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "cortex-vec"
    stub.write_text(
        "#!/bin/sh\n"
        "echo 'cortex-vec: unavailable (smoke-test stub)' >&2\n"
        "exit 127\n"
    )
    stub.chmod(0o755)
    return bindir


def _claude(prompt, stub_bin):
    env = {**os.environ}
    for name in _SCRUBBED:
        env.pop(name, None)
    env["PATH"] = f"{stub_bin}{os.pathsep}{env.get('PATH', '')}"
    env["CORTEX_SKIP_RECORD"] = "1"      # no Raw/ write from this session
    env["CORTEX_NO_CLASSIFIER"] = "1"    # no nested classifier calls
    return subprocess.run(
        ["claude", "-p", prompt, "--plugin-dir", str(REPO_ROOT)],
        capture_output=True, text=True, env=env, timeout=600,
    )


def test_query_command_resolves_and_reaches_the_skill(stub_bin):
    """It resolves under `cortexes:`, runs the skill, follows its no-vault path.

    With no `~/.cortex/config.json`, the skill's documented behaviour is to
    say so and point at genesis. Producing that — rather than an unknown
    command, a generic answer, or a silent no-op — is the evidence that the
    command reached `cortexes:cortex-query` through the body instruction.
    """
    r = _claude(f"/cortexes:query {SENTINEL}", stub_bin)
    assert r.returncode == 0, r.stderr
    out = (r.stdout + r.stderr).lower()
    assert "unknown command" not in out, r.stdout
    assert "genesis" in out, r.stdout


def test_old_namespace_does_not_resolve(stub_bin):
    r = _claude(f"/cortex:query {SENTINEL}", stub_bin)
    assert "Unknown command: /cortex:query" in r.stdout + r.stderr, r.stdout
