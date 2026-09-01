"""Regression tests for the context session-start-inject.sh injects.

The injected text is a prompt: it is the only place the retrieval policy
reaches the model at session start, so its wording is behaviour, not prose.
These tests pin the narrow using-cortex policy — four concrete signals, and
an opt-out that actually sticks — against the broad "search proactively
regardless" wording it replaced in 2.0.0.

Baton/menu plumbing is covered in test_takeoff.py; this file only covers the
policy block and the vault-topic metadata.
"""
import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INJECT = REPO_ROOT / "hooks" / "scripts" / "session-start-inject.sh"


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _make_repo(path, origin="https://example.com/acme/myrepo.git"):
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "remote", "add", "origin", origin)
    return path


def _run_inject(cwd, vault):
    env = {**os.environ, "CORTEX_VAULT_PATH": str(vault)}
    res = subprocess.run(
        ["bash", str(INJECT)], input=json.dumps({"cwd": str(cwd)}),
        capture_output=True, text=True, env=env,
    )
    assert res.returncode == 0, res.stderr
    if not res.stdout.strip():
        return ""
    return json.loads(res.stdout)["hookSpecificOutput"]["additionalContext"]


def _vault(tmp_path, notes=("Nginx",), projects=("cortexes",), note_body="secret body"):
    v = tmp_path / "vault"
    for topic in notes:
        (v / "Notes" / topic).mkdir(parents=True)
        (v / "Notes" / topic / "page.md").write_text(note_body)
    for proj in projects:
        (v / "Projects" / proj).mkdir(parents=True)
        (v / "Projects" / proj / "page.md").write_text(note_body)
    v.mkdir(exist_ok=True)
    return v


def _ctx(tmp_path, **kw):
    vault = _vault(tmp_path, **kw)
    repo = _make_repo(tmp_path / "work")
    return _run_inject(repo, vault)


# --- branding ---

def test_label_is_cortexes(tmp_path):
    ctx = _ctx(tmp_path)
    assert ctx.startswith("[Cortexes]")
    assert "[Cortex]" not in ctx


# --- the four signals replace the old proactive rule ---

def test_lists_the_four_using_cortex_signals(tmp_path):
    ctx = _ctx(tmp_path)
    assert "四個訊號" in ctx
    for n in ("1.", "2.", "3.", "4."):
        assert n in ctx
    # Signal wording, one probe per signal.
    assert "明確要求" in ctx          # 1 explicit request
    assert "之前那個" in ctx          # 2 reference to prior work
    assert "實際列出" in ctx          # 3 a topic actually listed
    assert "接續" in ctx              # 4 resuming a session
    assert "using-cortex" in ctx


def test_no_unconditional_proactive_search_rule(tmp_path):
    ctx = _ctx(tmp_path)
    # The 1.x wording: fire regardless of the menu choice.
    assert "無論使用者是否選" not in ctx
    assert "即使使用者選 4" not in ctx


def test_no_ongoing_project_default_assumption(tmp_path):
    ctx = _ctx(tmp_path)
    assert "預設假設 vault 有 prior context" not in ctx
    assert "先查再說" not in ctx


def test_no_search_one_extra_time_rule(tmp_path):
    ctx = _ctx(tmp_path)
    assert "寧可多查一次" not in ctx
    assert "成本遠低於" not in ctx


def test_difficulty_is_explicitly_not_a_signal(tmp_path):
    ctx = _ctx(tmp_path)
    assert "都不是**訊號" in ctx
    assert "直接回答" in ctx


# --- option 4 / skipping the menu suppresses lookup for the session ---

def test_option_4_suppresses_proactive_lookup_for_the_session(tmp_path):
    ctx = _ctx(tmp_path)
    assert "略過此選單" in ctx
    assert "不再**主動查 vault" in ctx
    assert "訊號 2-4 一律不觸發" in ctx


def test_option_4_still_allows_a_later_explicit_request(tmp_path):
    ctx = _ctx(tmp_path)
    assert "明確要求（訊號 1）才查" in ctx


# --- topic list is metadata, not content ---

def test_surfaces_topic_names_not_note_contents(tmp_path):
    ctx = _ctx(tmp_path, notes=("Nginx",), projects=("cortexes",),
               note_body="SENTINEL-NOTE-BODY")
    assert "Notes/: Nginx" in ctx
    assert "Projects/: cortexes" in ctx
    assert "SENTINEL-NOTE-BODY" not in ctx


def test_empty_vault_sections_render_placeholder(tmp_path):
    ctx = _ctx(tmp_path, notes=(), projects=())
    assert "Notes/: (空)" in ctx
    assert "Projects/: (空)" in ctx


# --- the menu itself is unchanged ---

def test_menu_still_offers_four_options_and_defers_raw_scan(tmp_path):
    ctx = _ctx(tmp_path)
    assert "4. 直接開始工作" in ctx
    assert "不要在使用者選擇前預先掃描 Raw/" in ctx


# --- no vault configured ---

def test_no_vault_configured_emits_nothing(tmp_path):
    repo = _make_repo(tmp_path / "work")
    assert _run_inject(repo, tmp_path / "nope") == ""
