"""The raw auto-commit carries this hook's own paths and nothing else.

The vault index is shared by every concurrent session. session-end-record.sh
used to run a bare `git commit`, so a distill that had staged a new page and
paused for the user's approval lost it to the next session's raw commit. A
raw commit has no allow trailer, the remote's secrets hook crashed on the
quoted non-ASCII path of that page, and every later push was refused until history was rewritten. The commit is now
path-scoped: the Raw just written plus whatever reclaim removed.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORD = REPO_ROOT / "hooks" / "scripts" / "session-end-record.sh"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x",
}

# the shape that crashed the remote hook: non-ASCII *and* spaces, added as a new file
FOREIGN_PAGE = "Projects/webapp/路由比對 的 case-sensitive EndsWith.md"

_LINE = json.dumps({"type": "assistant",
                    "message": {"content": [{"type": "text", "text": "x" * 200}]}}) + "\n"


def _git(cwd, *args):
    # core.quotepath=false: paths come back as written, not octal-escaped
    return subprocess.run(["git", "-C", str(cwd), "-c", "core.quotepath=false", *args],
                          check=True, capture_output=True, text=True,
                          env={**os.environ, **GIT_ENV})


def _vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    _git(vault, "init", "-q", "-b", "main")
    (vault / "README.md").write_text("vault\n")
    _git(vault, "add", "README.md")
    _git(vault, "commit", "-q", "-m", "init")
    return vault


def _home(tmp_path, vault):
    home = tmp_path / "home"
    (home / ".cortex").mkdir(parents=True)
    (home / ".cortex" / "config.json").write_text(json.dumps({
        "vault_path": str(vault),
        "git": {"auto_commit": True, "auto_push": False},
    }))
    return home


def _transcript(tmp_path, lines=40):
    tx = tmp_path / "transcript.jsonl"
    tx.write_text(_LINE * lines)
    return tx


def _work_repo(tmp_path):
    cwd = tmp_path / "work"
    cwd.mkdir()
    _git(cwd, "init", "-q")
    _git(cwd, "remote", "add", "origin", "git@example.invalid:team/demo.git")
    return cwd


def _run(home, tx, cwd):
    env = {**os.environ, **GIT_ENV, "HOME": str(home)}
    for k in ("CORTEX_SESSION_RECORDING", "CORTEX_SKIP_RECORD", "CORTEX_FILTER_TIMEOUT"):
        env.pop(k, None)
    r = subprocess.run(["bash", str(RECORD)],
                       input=json.dumps({"transcript_path": str(tx), "cwd": str(cwd)}),
                       text=True, capture_output=True, env=env)
    assert r.returncode == 0, r.stderr
    return r


def _wait_for(pred, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.5)
    return pred()


def _subjects(vault):
    return _git(vault, "log", "--format=%s").stdout.splitlines()


def _changed(vault, rev="HEAD"):
    """{path: status} of one commit, e.g. {"Raw/…/x.md": "A"}."""
    # --no-renames: a D + A pair in one commit must not be folded into R100
    out = _git(vault, "show", "--name-status", "--no-renames", "--format=", rev).stdout
    return {line.split("\t", 1)[1]: line[0] for line in out.splitlines() if line}


def test_raw_commit_leaves_another_sessions_staged_page_alone(tmp_path):
    # Break: `git commit` without a pathspec → the page rides along in the raw
    # commit, the other session's own commit comes back "nothing to commit",
    # and the raw commit now adds a quoted path with no allow trailer.
    vault = _vault(tmp_path)
    page = vault / FOREIGN_PAGE
    page.parent.mkdir(parents=True)
    page.write_text("---\ntitle: x\n---\n")
    _git(vault, "add", "--", FOREIGN_PAGE)  # another session, mid-distill, waiting for its ok

    _run(_home(tmp_path, vault), _transcript(tmp_path), _work_repo(tmp_path))
    assert _wait_for(lambda: _subjects(vault)[0].startswith("raw: session demo"))

    changed = _changed(vault)
    assert len(changed) == 1 and all(p.startswith("Raw/") for p in changed), changed
    # the page is exactly where the other session left it: staged, not committed
    assert FOREIGN_PAGE in _git(vault, "diff", "--cached", "--name-only").stdout.splitlines()
    assert FOREIGN_PAGE not in _git(vault, "ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines()


def test_raw_commit_still_carries_the_snapshot_reclaim_removed(tmp_path):
    # Break: pathspec = the new Raw only → reclaim's `git rm` stays staged and
    # the superseded snapshot's deletion is left for someone else's commit,
    # under someone else's subject line.
    vault = _vault(tmp_path)
    home = _home(tmp_path, vault)
    tx = _transcript(tmp_path)
    cwd = _work_repo(tmp_path)

    _run(home, tx, cwd)
    assert _wait_for(lambda: len(_subjects(vault)) == 2)
    (first,) = _changed(vault)
    assert first.startswith("Raw/")

    # SessionEnd fires again on the same, now longer, transcript: the Raw it
    # writes supersedes the first one, which reclaim removes with `git rm`.
    time.sleep(1.1)  # Raw filenames carry HHMMSS
    with tx.open("a") as f:
        f.write(_LINE * 20)
    _run(home, tx, cwd)
    assert _wait_for(lambda: len(_subjects(vault)) == 3)

    assert "(reclaimed 1 superseded)" in _subjects(vault)[0]
    changed = _changed(vault)
    assert changed.get(first) == "D", changed
    added = [p for p, s in changed.items() if s == "A"]
    assert len(added) == 1 and added[0].startswith("Raw/") and added[0] != first, changed
    assert set(changed) == {first, added[0]}, changed
