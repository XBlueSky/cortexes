"""SessionStart deck: the fenced menu block and its machine-readable first line.

session-start-inject.sh wraps the model-facing menu in sentinels and writes a
JSON deck on the line after the opening one. The cortexes mod (hooks/deck.tsx)
draws the deck as a band and cuts the block from the model's context; without
the mod the block reaches the model as before. These tests pin the contract
the mod reads.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INJECT = REPO_ROOT / "hooks" / "scripts" / "session-start-inject.sh"

MENU_START = "<!-- cortex:menu -->"
MENU_END = "<!-- /cortex:menu -->"
DECK_PREFIX = "<!-- cortex:deck "
DECK_SUFFIX = " -->"


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _make_repo(path, origin="https://example.com/acme/myrepo.git"):
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "remote", "add", "origin", origin)
    return path


def _write_baton(vault, slug, topic, summary="s", workdir=None):
    p = vault / ".takeoff" / slug / f"{topic}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = [f"repo: {slug}", f"topic: {topic}"]
    if workdir is not None:
        fm.append(f"workdir: {workdir}")
    fm.append(f"summary: {summary}")
    p.write_text("---\n" + "\n".join(fm) + "\n---\nbody\n")
    return p


def _inject(cwd, vault, plugin_root=None, **fields):
    env = {**os.environ, "CORTEX_VAULT_PATH": str(vault)}
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    if plugin_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    res = subprocess.run(["bash", str(INJECT)],
                         input=json.dumps({"cwd": str(cwd), **fields}),
                         capture_output=True, text=True, env=env)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)["hookSpecificOutput"]["additionalContext"]


def _deck_line(ctx):
    start = ctx.index(MENU_START + "\n") + len(MENU_START) + 1
    line = ctx[start:].split("\n", 1)[0]
    assert line.startswith(DECK_PREFIX) and line.endswith(DECK_SUFFIX), line
    return line


def _deck(ctx):
    line = _deck_line(ctx)
    return json.loads(line[len(DECK_PREFIX):-len(DECK_SUFFIX)])


def test_menu_is_fenced_once_and_the_front_stays_outside(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    ctx = _inject(_make_repo(tmp_path / "work"), vault)
    assert ctx.count(MENU_START) == 1 and ctx.count(MENU_END) == 1
    start, end = ctx.index(MENU_START), ctx.index(MENU_END)
    assert ctx.index("Vault 目前涵蓋的主題") < start
    assert ctx.index("何時查 vault") < start
    assert start < ctx.index("在你第一次回覆使用者時") < end
    assert start < ctx.index("直接開始工作」或略過此選單時") < end
    assert ctx.rstrip().endswith(MENU_END)


def test_deck_carries_status_actions_and_handoff(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    deck = _deck(_inject(_make_repo(tmp_path / "work"), vault))
    assert deck["v"] == 1
    assert deck["source"] == "startup"
    assert deck["repo"] == "myrepo"
    assert deck["status"] == []
    assert [a["label"] for a in deck["actions"]] == ["載入記憶", "最近紀錄", "處理待辦"]
    assert deck["actions"][0]["prompt"] == "載入此 repo 的記憶筆記（執行 cortex-vec search --repo myrepo）"
    assert deck["actions"][1]["prompt"] == f"查看最近的 session 紀錄（列出 {vault}/Raw/ 中最近幾筆）"
    assert deck["actions"][2]["prompt"] == (
        "處理待辦事項（提煉未處理的紀錄）。"
        f"找未提煉的紀錄用 cortex-vec distill-queue --root {vault}/Raw；"
        "不要用 grep 找 marker：meta-session 內文會引用該字串騙過 grep。")
    assert deck["batons"] == []
    assert deck["handoff"] == "context 用量接近上限，用 cortex-takeoff skill 建立交接。"


@pytest.mark.parametrize("source", ["resume", "clear", "compact"])
def test_deck_source_follows_session_start(tmp_path, source):
    vault = tmp_path / "vault"
    vault.mkdir()
    deck = _deck(_inject(_make_repo(tmp_path / "work"), vault, source=source))
    assert deck["source"] == source


def test_deck_batons_follow_the_text_menu_order(tmp_path):
    vault = tmp_path / "vault"
    repo = _make_repo(tmp_path / "work")
    older = _write_baton(vault, "myrepo", "old-line", summary="older work")
    newer = _write_baton(vault, "myrepo", "new-line", summary="newer work")
    now = time.time()
    os.utime(older, (now - 300, now - 300))
    os.utime(newer, (now - 100, now - 100))
    ctx = _inject(repo, vault)
    assert ctx.index("5. 載入交接［new-line］") < ctx.index("6. 載入交接［old-line］")
    assert _deck(ctx)["batons"] == [
        {"label": "new-line", "summary": "newer work",
         "prompt": "載入交接［new-line］：用 cortex-takeoff skill 的 resume 流程讀取 "
                   "topic new-line 的交接文件全文，採納為續傳脈絡接續工作；不要刪除該檔。"},
        {"label": "old-line", "summary": "older work",
         "prompt": "載入交接［old-line］：用 cortex-takeoff skill 的 resume 流程讀取 "
                   "topic old-line 的交接文件全文，採納為續傳脈絡接續工作；不要刪除該檔。"},
    ]


def test_deck_baton_without_summary_carries_none(tmp_path):
    vault = tmp_path / "vault"
    repo = _make_repo(tmp_path / "work")
    _write_baton(vault, "myrepo", "bare", summary="")
    ctx = _inject(repo, vault)
    assert "5. 載入交接［bare］：(無摘要)" in ctx
    assert "summary" not in _deck(ctx)["batons"][0]


def test_deck_baton_label_marks_a_foreign_workdir(tmp_path):
    vault = tmp_path / "vault"
    repo = _make_repo(tmp_path / "work")
    _write_baton(vault, "myrepo", "mine", workdir=os.path.realpath(str(repo)))
    _write_baton(vault, "myrepo", "theirs", workdir="/somewhere/else")
    labels = {b["label"] for b in _deck(_inject(repo, vault))["batons"]}
    assert labels == {"mine", "theirs（來自 /somewhere/else）"}


def test_deck_line_cannot_close_the_comment_early(tmp_path):
    vault = tmp_path / "vault"
    repo = _make_repo(tmp_path / "work")
    odd = '/tmp/a-->b<!-- /cortex:menu --> & "q" \\ z'
    _write_baton(vault, "myrepo", "theirs", workdir=odd)
    ctx = _inject(repo, vault)
    body = _deck_line(ctx)[len(DECK_PREFIX):-len(DECK_SUFFIX)]
    assert "<" not in body and ">" not in body
    assert _deck(ctx)["batons"][0]["label"] == f"theirs（來自 {odd}）"


# --- The deck file: the mod's channel where an organization's policy plugin
# keeps session.append from the person's plugins (hooks/deck.tsx polls it).

def _deck_file(plugin_root, session_id):
    return plugin_root / ".deck" / f"{session_id}.json"


def test_deck_file_carries_the_context_deck(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    plug = tmp_path / "plug"
    ctx = _inject(_make_repo(tmp_path / "work"), vault, plugin_root=plug, session_id="sess-1")
    assert json.loads(_deck_file(plug, "sess-1").read_text()) == _deck(ctx)


def test_deck_stamp_differs_per_run(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    repo = _make_repo(tmp_path / "work")
    first = _deck(_inject(repo, vault))["stamp"]
    second = _deck(_inject(repo, vault))["stamp"]
    assert isinstance(first, str) and first and first != second


@pytest.mark.parametrize("session_id", [None, "", "../escape", "a/b"])
def test_no_deck_file_without_a_plain_session_id(tmp_path, session_id):
    vault = tmp_path / "vault"
    vault.mkdir()
    plug = tmp_path / "plug"
    fields = {} if session_id is None else {"session_id": session_id}
    _inject(_make_repo(tmp_path / "work"), vault, plugin_root=plug, **fields)
    assert not (tmp_path / "escape.json").exists()
    assert list(plug.rglob("*.json")) == []


def test_no_deck_file_without_a_plugin_root(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    ctx = _inject(_make_repo(tmp_path / "work"), vault, session_id="sess-1")
    assert MENU_START in ctx


def test_old_deck_files_are_swept(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    plug = tmp_path / "plug"
    (plug / ".deck").mkdir(parents=True)
    old, recent = _deck_file(plug, "old"), _deck_file(plug, "recent")
    old.write_text("{}")
    recent.write_text("{}")
    two_days_ago = time.time() - 2 * 86400
    os.utime(old, (two_days_ago, two_days_ago))
    _inject(_make_repo(tmp_path / "work"), vault, plugin_root=plug, session_id="sess-1")
    assert not old.exists()
    assert recent.exists() and _deck_file(plug, "sess-1").exists()
