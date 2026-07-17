"""SessionEnd recording guard: CORTEX_SKIP_RECORD suppresses the Raw write.

session-end-record.sh does `mkdir -p "$target_dir"` synchronously (before it
detaches the async writer via nohup), so "was Raw/ created?" is a race-free
signal for whether the script proceeded past the opt-out guard.
"""
import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORD = REPO_ROOT / "hooks" / "scripts" / "session-end-record.sh"


def _setup(tmp_path):
    home = tmp_path / "home"
    (home / ".cortex").mkdir(parents=True)
    vault = tmp_path / "vault"
    vault.mkdir()
    (home / ".cortex" / "config.json").write_text(
        json.dumps({"vault_path": str(vault)})
    )
    # A transcript comfortably over the 4096-byte size gate so the script
    # reaches the recording logic.
    tx = tmp_path / "transcript.jsonl"
    line = json.dumps(
        {"type": "assistant",
         "message": {"content": [{"type": "text", "text": "x" * 200}]}}
    )
    tx.write_text((line + "\n") * 40)
    assert tx.stat().st_size >= 4096
    cwd = tmp_path / "work"
    cwd.mkdir()
    return home, vault, tx, cwd


def _run(home, tx, cwd, extra_env=None):
    env = {**os.environ, "HOME": str(home)}
    env.pop("CORTEX_SESSION_RECORDING", None)
    env.pop("CORTEX_SKIP_RECORD", None)
    if extra_env:
        env.update(extra_env)
    stdin = json.dumps({"transcript_path": str(tx), "cwd": str(cwd)})
    return subprocess.run(
        ["bash", str(RECORD)], input=stdin, text=True,
        capture_output=True, env=env,
    )


def test_skip_record_env_suppresses_raw(tmp_path):
    home, vault, tx, cwd = _setup(tmp_path)
    r = _run(home, tx, cwd, {"CORTEX_SKIP_RECORD": "1"})
    assert r.returncode == 0
    # Guard exits before the synchronous mkdir, so no Raw tree is created.
    assert not (vault / "Raw").exists()


def test_without_skip_env_proceeds_to_record(tmp_path):
    home, vault, tx, cwd = _setup(tmp_path)
    r = _run(home, tx, cwd)
    assert r.returncode == 0
    # No opt-out: the script proceeds and synchronously creates the Raw dir.
    assert (vault / "Raw").exists()
