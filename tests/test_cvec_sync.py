"""cortex-vec follows the plugin without a manual reinstall.

`/plugin update` refreshes the plugin cache but leaves the pip-installed
cortex-vec CLI behind, and the manual reinstall was easy to forget. At
SessionStart, cvec_sync.py compares the installed package with the copy the
plugin ships, reinstalls it in the background when they differ, and reports
each stage (updating / updated / failed) as a status line.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cvec_fixtures import check_cmd, make_layout, run_check, wait_settled

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

from cvec_sync import decide, tree_hash  # noqa: E402

RUNNING = "cortex-vec 正在背景更新為 plugin 9.9.9 附帶版本"
UPDATED = "cortex-vec 已更新（plugin 9.9.9）"


def _status(out: str) -> dict | None:
    out = out.strip()
    return json.loads(out) if out else None


# --- tree_hash ---------------------------------------------------------------

def test_tree_hash_ignores_pycache_and_pyc(tmp_path):
    pkg = tmp_path / "cortex_vec"
    pkg.mkdir()
    (pkg / "a.py").write_text("x = 1\n")
    before = tree_hash(pkg)
    (pkg / "__pycache__").mkdir()
    (pkg / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\0junk")
    (pkg / "stray.pyc").write_bytes(b"\0junk")
    assert tree_hash(pkg) == before
    (pkg / "a.py").write_text("x = 2\n")
    changed = tree_hash(pkg)
    assert changed != before
    (pkg / "editor.html").write_text("<p>")
    assert tree_hash(pkg) != changed


# --- decide ------------------------------------------------------------------

B, OTHER = "bundled", "other"


def _st(status, target=B, reported=False):
    return {"target_hash": target, "plugin_version": "9.9.9", "status": status,
            "reported": reported}


@pytest.mark.parametrize("installed,state,lock_free,want", [
    (B, None, True, "none"),
    (OTHER, None, True, "start"),
    (OTHER, None, False, "running"),
    (OTHER, _st("failed"), True, "failed"),
    (OTHER, _st("failed", target=OTHER), True, "start"),
    (B, _st("ok"), True, "ok"),
    (B, _st("ok", reported=True), True, "none"),
    (OTHER, _st("running"), False, "running"),
    (OTHER, _st("running"), True, "failed"),
    (B, _st("failed"), True, "recheck"),
    (B, _st("failed", target=OTHER), True, "none"),
])
def test_decide_table(installed, state, lock_free, want):
    assert decide(B, installed, state, lock_free) == want


# --- check: silent cases -----------------------------------------------------

def test_check_silent_when_same(tmp_path):
    lay = make_layout(tmp_path, same=True)
    assert run_check(lay) == ""
    assert lay.pip_calls() == 0


def test_check_silent_without_bundled_dir(tmp_path):
    lay = make_layout(tmp_path, bundled=False)
    assert run_check(lay) == ""


def test_check_silent_when_not_installed(tmp_path):
    lay = make_layout(tmp_path)
    assert run_check(lay, with_site=False) == ""
    assert lay.pip_calls() == 0


def test_check_silent_for_editable_install(tmp_path):
    lay = make_layout(tmp_path, editable=True)
    assert run_check(lay) == ""
    assert lay.pip_calls() == 0


def test_check_survives_corrupt_state(tmp_path):
    lay = make_layout(tmp_path)
    lay.state_file.parent.mkdir(parents=True)
    lay.state_file.write_text("{")
    assert _status(run_check(lay)) == {"text": RUNNING, "warn": False}
    wait_settled(lay)


# --- check: the update cycle -------------------------------------------------

def test_check_starts_worker_then_reports_ok_once(tmp_path):
    lay = make_layout(tmp_path)
    assert _status(run_check(lay)) == {"text": RUNNING, "warn": False}
    assert wait_settled(lay)["status"] == "ok"
    assert (lay.site / "cortex_vec" / "__init__.py").read_text() == "MARKER = 'new'\n"
    assert _status(run_check(lay)) == {"text": UPDATED, "warn": False}
    assert run_check(lay) == ""
    assert lay.pip_calls() == 1


def test_failed_install_warns_and_does_not_retry(tmp_path):
    lay = make_layout(tmp_path)
    run_check(lay, mode="fail")
    assert wait_settled(lay)["status"] == "failed"
    for _ in range(2):
        st = _status(run_check(lay, mode="fail"))
        assert st["warn"] is True
        assert st["text"].startswith("cortex-vec 自動更新失敗（log: ")
        assert st["text"].endswith(
            f"pip install --force-reinstall --no-deps {lay.plugin}/cortex-vec"
            f" && pip install {lay.plugin}/cortex-vec")
    assert lay.pip_calls() == 1
    log = st["text"].split("log: ", 1)[1].split("）", 1)[0]
    assert "fake pip: boom" in Path(log).read_text()


def test_concurrent_checks_run_pip_once(tmp_path):
    lay = make_layout(tmp_path)
    env = lay.env(sleep=0.5)
    procs = [subprocess.Popen(check_cmd(lay), env=env, stdout=subprocess.PIPE, text=True)
             for _ in range(2)]
    outs = [p.communicate(timeout=20)[0] for p in procs]
    assert all(_status(o) == {"text": RUNNING, "warn": False} for o in outs)
    assert wait_settled(lay)["status"] == "ok"
    assert lay.pip_calls() == 1


def test_stale_running_reports_failed(tmp_path):
    lay = make_layout(tmp_path)
    bundled = tree_hash(lay.bundled_pkg)
    lay.state_file.parent.mkdir(parents=True)
    lay.state_file.write_text(json.dumps(_st("running", target=bundled)))
    st = _status(run_check(lay))
    assert st["warn"] is True and st["text"].startswith("cortex-vec 自動更新失敗")
    assert lay.state()["status"] == "failed"
    assert lay.pip_calls() == 0


def test_broken_cli_after_matching_install_keeps_warning_until_fixed(tmp_path):
    # pip succeeds and the files match, but the CLI cannot start (a dependency
    # the new copy needs is missing). Later sessions must keep warning; once
    # the dependency shows up, the warning clears without another pip run.
    lay = make_layout(tmp_path, needs_dep=True)
    run_check(lay)
    assert wait_settled(lay)["status"] == "failed"
    for _ in range(2):
        st = _status(run_check(lay))
        assert st is not None and st["warn"] is True
        assert st["text"].startswith("cortex-vec 自動更新失敗")
    (lay.site / "cvec_fakedep.py").write_text("")
    assert run_check(lay) == ""
    assert run_check(lay) == ""
    assert lay.pip_calls() == 1


def test_missing_dependency_fails_verification_until_installed(tmp_path):
    # The CLI imports its subcommands lazily, so `--help` alone starts fine
    # without them; the new copy's dependency list is checked as well.
    lay = make_layout(tmp_path)
    run_check(lay, requires="cvec-fakedep2>=1.0,docs-only; extra == \"docs\"")
    assert wait_settled(lay)["status"] == "failed"
    st = _status(run_check(lay))
    assert st is not None and st["warn"] is True
    dist = lay.site / "cvec_fakedep2-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: cvec-fakedep2\nVersion: 1.0\n")
    assert run_check(lay) == ""
    assert "cvec-fakedep2" in Path(lay.home / ".cortex" / "cvec-sync" / "install.log").read_text()


def test_source_tree_on_pythonpath_does_not_stand_in_for_the_install(tmp_path):
    # A checkout ahead of site-packages on PYTHONPATH wins `import cortex_vec`,
    # but the sync owns the pip-installed copy: hash and verify that one.
    from cvec_fixtures import _write_pkg
    lay = make_layout(tmp_path)
    shadow = tmp_path / "checkout"
    _write_pkg(shadow / "cortex_vec", "dev")
    assert _status(run_check(lay, front=shadow)) == {"text": RUNNING, "warn": False}
    assert wait_settled(lay)["status"] == "ok"
    assert (lay.site / "cortex_vec" / "__init__.py").read_text() == "MARKER = 'new'\n"
    assert _status(run_check(lay, front=shadow)) == {"text": UPDATED, "warn": False}
    assert run_check(lay, front=shadow) == ""
