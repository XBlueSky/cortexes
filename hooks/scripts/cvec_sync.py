#!/usr/bin/env python3
"""Keep the pip-installed cortex-vec CLI in step with the plugin that ships it.

`/plugin update` refreshes the plugin cache but not the CLI, and the manual
`pip install --force-reinstall` that should follow was easy to forget. The
plugin cache already carries cortex-vec's source, so SessionStart compares it
with the installed package and, when they differ, reinstalls that exact copy
in the background -- no network, no ssh key, never newer than the plugin.

The comparison hashes file contents, not version numbers or commits: the
package version stays put across many releases (which is why `pip install -U`
skipped the reinstall), and most plugin commits never touch cortex-vec.

Subcommands:
  check   --plugin-root DIR   fast; prints one status line as JSON, or nothing
  install --plugin-root DIR --target HASH
                              the background worker that `check` spawns

State lives in ~/.cortex/cvec-sync/ (state.json, install.log, lock). A hash
that failed once is not retried until the plugin ships a different copy, so
a broken install warns every session instead of rerunning pip every session.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path

STATE_DIR = Path.home() / ".cortex" / "cvec-sync"
STATE_FILE = STATE_DIR / "state.json"
LOG_FILE = STATE_DIR / "install.log"
LOCK_FILE = STATE_DIR / "lock"


def tree_hash(pkg_dir: Path) -> str:
    """Hashes a package directory's files, ignoring bytecode caches."""
    h = hashlib.sha256()
    files = sorted(p for p in pkg_dir.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    for p in files:
        h.update(p.relative_to(pkg_dir).as_posix().encode() + b"\0")
        h.update(p.read_bytes() + b"\0")
    return h.hexdigest()


def installed_pkg() -> tuple[Path, bool] | None:
    """Returns (installed cortex_vec directory, is_editable), or None when absent.

    The directory comes from the distribution's own files, not from the import
    system: a source checkout ahead of site-packages on PYTHONPATH wins
    `import cortex_vec`, but the sync owns the copy pip installed.
    """
    try:
        dist = importlib.metadata.distribution("cortex-vec")
    except importlib.metadata.PackageNotFoundError:
        return None
    editable = False
    raw = dist.read_text("direct_url.json")
    if raw:
        try:
            editable = bool(json.loads(raw).get("dir_info", {}).get("editable"))
        except (ValueError, AttributeError):
            pass
    pkg = Path(dist.locate_file("cortex_vec"))
    if not editable and not pkg.is_dir():
        return None
    return pkg, editable


def decide(bundled: str, installed: str, state: dict | None, lock_free: bool) -> str:
    """Picks what `check` does: none, start, running, ok, failed or recheck.

    Only a state recorded for the bundled hash counts; one for an older copy
    says nothing about this one. A `running` state whose lock nobody holds is
    a worker that died, so it counts as a failure. A failure whose files
    nonetheless match (pip succeeded, the CLI would not start) cannot be told
    from a manual fix by hashes alone, so `check` re-runs the CLI: recheck.
    """
    same = bundled == installed
    st = state if state and state.get("target_hash") == bundled else None
    if st and st.get("status") == "running":
        if not lock_free:
            return "running"
        st = {**st, "status": "failed"}
    if same:
        if st and st.get("status") == "failed":
            return "recheck"
        return "ok" if st and st.get("status") == "ok" and not st.get("reported") else "none"
    if st and st.get("status") == "failed":
        return "failed"
    return "start" if lock_free else "running"


def _read_state() -> dict | None:
    try:
        data = json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_state(**fields) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_name(f"state.json.{os.getpid()}")
    tmp.write_text(json.dumps(fields))
    os.replace(tmp, STATE_FILE)


def _plugin_version(root: Path) -> str:
    try:
        return json.loads((root / ".claude-plugin" / "plugin.json").read_text())["version"]
    except (OSError, ValueError, KeyError, TypeError):
        return "unknown"


def _check(root: Path) -> dict | None:
    bundled_pkg = root / "cortex-vec" / "src" / "cortex_vec"
    if not bundled_pkg.is_dir():
        return None
    found = installed_pkg()
    if found is None or found[1]:
        return None
    bundled = tree_hash(bundled_pkg)
    version = _plugin_version(root)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock_free = True
        except BlockingIOError:
            lock_free = False
        # Read the install and the state only after probing the lock: a worker
        # that finishes in between would otherwise leave an old hash next to a
        # free lock, and its "running" state would read as a dead worker.
        installed = tree_hash(found[0])
        state = _read_state()
        action = decide(bundled, installed, state, lock_free)

        if action == "start":
            # The worker inherits the lock this process holds: a check in
            # another session never sees "running" with a free lock while the
            # worker is still starting up.
            _write_state(target_hash=bundled, plugin_version=version,
                         status="running", reported=False)
            with open(LOG_FILE, "w") as log:
                subprocess.Popen(
                    [sys.executable, __file__, "install", "--plugin-root", str(root),
                     "--target", bundled],
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=True, pass_fds=(lock_fd,))
    finally:
        os.close(lock_fd)

    if action == "recheck":
        if _cli_works(stderr=subprocess.DEVNULL):
            _write_state(**{**state, "status": "ok", "reported": True})
            return None
        action = "failed"
    if action == "none":
        return None
    if action in ("start", "running"):
        return {"text": f"cortex-vec 正在背景更新為 plugin {version} 附帶版本", "warn": False}
    if action == "ok":
        _write_state(**{**state, "reported": True})
        return {"text": f"cortex-vec 已更新（plugin {version}）", "warn": False}
    if state and state.get("status") == "running":
        _write_state(**{**state, "status": "failed"})
    # Reinstall the package alone, then let a plain install fill in a missing
    # dependency without force-reinstalling the whole tree under it.
    project = root / "cortex-vec"
    return {"text": f"cortex-vec 自動更新失敗（log: {LOG_FILE}），請手動執行："
                    f"pip install --force-reinstall --no-deps {project}"
                    f" && pip install {project}", "warn": True}


# Every dependency cortex-vec declares (extras and marker-gated ones aside) must
# be installed: the CLI imports its subcommands lazily, so `--help` starts fine
# without them and only a real command would fail.
_DEPS_PRESENT = """\
import importlib.metadata as m, re, sys
missing = []
for req in m.requires("cortex-vec") or []:
    if ";" in req:
        continue
    name = re.match(r"[A-Za-z0-9._-]+", req).group(0)
    try:
        m.distribution(name)
    except m.PackageNotFoundError:
        missing.append(name)
if missing:
    print("cvec-sync: missing dependencies: " + ", ".join(missing), file=sys.stderr)
    sys.exit(1)
"""


def _cli_works(stderr=None) -> bool:
    """Checks the installed CLI in a fresh interpreter, away from the session's cwd:
    its declared dependencies are installed and `cortex-vec --help` runs."""
    for args in (["-c", _DEPS_PRESENT], ["-m", "cortex_vec.cli", "--help"]):
        if subprocess.run([sys.executable, *args], stdout=subprocess.DEVNULL,
                          stderr=stderr, cwd=STATE_DIR).returncode != 0:
            return False
    return True


def _install(root: Path, target: str) -> int:
    """Reinstalls the bundled copy, verifies it, and records the outcome."""
    py = sys.executable
    pip = subprocess.run([py, "-m", "pip", "install", "--no-deps", "--force-reinstall",
                          str(root / "cortex-vec")])
    ok = pip.returncode == 0
    if ok:
        # A fresh interpreter: this process's import system predates the install.
        where = subprocess.run([py, "-c", "import importlib.metadata as m; print(m.distribution("
                                "'cortex-vec').locate_file('cortex_vec'))"],
                               capture_output=True, text=True, cwd=STATE_DIR)
        ok = where.returncode == 0 and tree_hash(Path(where.stdout.strip())) == target
        if not ok:
            print(f"cvec-sync: installed copy does not match the plugin's ({where.stderr.strip()})")
    if ok:
        ok = _cli_works()
        if not ok:
            print("cvec-sync: the installed CLI does not work (see above)")
    _write_state(target_hash=target, plugin_version=_plugin_version(root),
                 status="ok" if ok else "failed", reported=False)
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="cvec_sync")
    ap.add_argument("command", choices=("check", "install"))
    ap.add_argument("--plugin-root", required=True, type=Path)
    ap.add_argument("--target")
    args = ap.parse_args(argv)
    if args.command == "install":
        return _install(args.plugin_root, args.target)
    try:
        status = _check(args.plugin_root)
    except Exception:  # noqa: BLE001 -- a session must start whatever happens here
        return 0
    if status:
        print(json.dumps(status, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
