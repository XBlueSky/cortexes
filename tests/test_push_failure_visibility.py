"""auto-push failures must leave a trace instead of vanishing.

session-end-record.sh used to run `git push 2>/dev/null || true`: a rejected
push (pre-receive hook, auth, network) left the vault silently behind, and
every later push failed the same way until someone noticed by accident.
Now a failed push appends the remote's message to ~/.cortex/push-failures.log,
and session-start-inject.sh tells the next session how many commits are
still unpushed.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORD = REPO_ROOT / "hooks" / "scripts" / "session-end-record.sh"
INJECT = REPO_ROOT / "hooks" / "scripts" / "session-start-inject.sh"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x",
}


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True,
                          env={**os.environ, **GIT_ENV})


def _vault_with_remote(tmp_path, reject_message=None):
    """A vault repo tracking a bare remote; optionally a remote that rejects pushes."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    vault = tmp_path / "vault"
    vault.mkdir()
    _git(vault, "init", "-q", "-b", "main")
    (vault / "README.md").write_text("vault\n")
    _git(vault, "add", "README.md")
    _git(vault, "commit", "-q", "-m", "init")
    _git(vault, "remote", "add", "origin", str(remote))
    _git(vault, "push", "-q", "-u", "origin", "main")
    if reject_message:
        # installed after the initial push so only the hook's own push is refused
        hook = remote / "hooks" / "pre-receive"
        hook.write_text(f"#!/bin/sh\necho '{reject_message}' >&2\nexit 1\n")
        hook.chmod(0o755)
    return vault


def _home(tmp_path, vault, auto_push):
    home = tmp_path / "home"
    (home / ".cortex").mkdir(parents=True)
    (home / ".cortex" / "config.json").write_text(json.dumps({
        "vault_path": str(vault),
        "git": {"auto_commit": True, "auto_push": auto_push},
    }))
    return home


def _transcript(tmp_path):
    tx = tmp_path / "transcript.jsonl"
    line = json.dumps({"type": "assistant",
                       "message": {"content": [{"type": "text", "text": "x" * 200}]}})
    tx.write_text((line + "\n") * 40)
    return tx


def _work_repo(tmp_path):
    cwd = tmp_path / "work"
    cwd.mkdir()
    _git(cwd, "init", "-q")
    _git(cwd, "remote", "add", "origin", "git@example.invalid:team/demo.git")
    return cwd


def _wait_for(pred, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.5)
    return pred()


def test_rejected_push_is_logged_with_remote_message(tmp_path):
    vault = _vault_with_remote(tmp_path, reject_message="GL-HOOK-ERR: nope")
    home = _home(tmp_path, vault, auto_push=True)
    tx = _transcript(tmp_path)
    cwd = _work_repo(tmp_path)
    env = {**os.environ, **GIT_ENV, "HOME": str(home)}
    env.pop("CORTEX_SESSION_RECORDING", None)
    r = subprocess.run(["bash", str(RECORD)],
                       input=json.dumps({"transcript_path": str(tx), "cwd": str(cwd)}),
                       text=True, capture_output=True, env=env)
    assert r.returncode == 0

    log = home / ".cortex" / "push-failures.log"
    assert _wait_for(log.exists), "push failure was not logged"
    text = log.read_text()
    assert "GL-HOOK-ERR: nope" in text
    assert "repo=demo" in text
    # the raw commit itself still landed locally
    assert "raw: session demo" in _git(vault, "log", "-1", "--format=%s").stdout


def test_successful_push_writes_no_log(tmp_path):
    vault = _vault_with_remote(tmp_path)
    home = _home(tmp_path, vault, auto_push=True)
    tx = _transcript(tmp_path)
    cwd = _work_repo(tmp_path)
    env = {**os.environ, **GIT_ENV, "HOME": str(home)}
    env.pop("CORTEX_SESSION_RECORDING", None)
    subprocess.run(["bash", str(RECORD)],
                   input=json.dumps({"transcript_path": str(tx), "cwd": str(cwd)}),
                   text=True, capture_output=True, env=env)
    # wait until the background job has pushed the raw commit
    assert _wait_for(lambda: "raw: session demo" in
                     _git(vault, "log", "-1", "--format=%s", "origin/main").stdout)
    assert not (home / ".cortex" / "push-failures.log").exists()


def _inject(home, cwd):
    env = {**os.environ, **GIT_ENV, "HOME": str(home)}
    env.pop("CORTEX_VAULT_PATH", None)
    r = subprocess.run(["bash", str(INJECT)], input=json.dumps({"cwd": str(cwd)}),
                       text=True, capture_output=True, env=env)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


def test_session_start_reports_unpushed_commit_count(tmp_path):
    vault = _vault_with_remote(tmp_path)
    for i in range(2):
        (vault / f"n{i}.md").write_text("x\n")
        _git(vault, "add", f"n{i}.md")
        _git(vault, "commit", "-q", "-m", f"raw: session x {i}")
    home = _home(tmp_path, vault, auto_push=True)
    cwd = _work_repo(tmp_path)
    ctx = _inject(home, cwd)
    assert "2 個 commit 尚未推送" in ctx
    assert "push-failures.log" in ctx


def test_session_start_is_quiet_when_everything_is_pushed(tmp_path):
    vault = _vault_with_remote(tmp_path)
    home = _home(tmp_path, vault, auto_push=True)
    cwd = _work_repo(tmp_path)
    ctx = _inject(home, cwd)
    assert "尚未推送" not in ctx
