"""Shared fixtures for the cortex-vec sync helper (hooks/scripts/cvec_sync.py).

A layout is a throwaway world the helper cannot tell from the real one:

- ``site/``    an installed ``cortex_vec`` plus its dist-info, found first via PYTHONPATH
- ``plugin/``  a plugin cache copy carrying ``cortex-vec/src/cortex_vec``
- ``fakepip/`` a ``pip`` package that shadows the real one for ``python -m pip``:
               it logs each call, then copies the bundled package into ``site/``
               (``FAKE_PIP_MODE=copy``) or exits 1 (``FAKE_PIP_MODE=fail``)
- ``home/``    HOME, so state lands in ``home/.cortex/cvec-sync``
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HELPER = REPO_ROOT / "hooks" / "scripts" / "cvec_sync.py"

_CLI = "import sys\nif __name__ == '__main__':\n    sys.exit(0)\n"

_FAKE_PIP = """\
import os, shutil, sys, time
from pathlib import Path
with open(os.environ["FAKE_PIP_LOG"], "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\\n")
time.sleep(float(os.environ.get("FAKE_PIP_SLEEP", "0")))
if os.environ.get("FAKE_PIP_MODE") == "fail":
    print("fake pip: boom", file=sys.stderr)
    sys.exit(1)
src = Path(sys.argv[-1]) / "src" / "cortex_vec"
dst = Path(os.environ["FAKE_PIP_SITE"]) / "cortex_vec"
shutil.rmtree(dst)
shutil.copytree(src, dst)
# Real pip also rewrites the dist metadata; FAKE_PIP_REQUIRES stands in for
# the new copy's dependency list ("a,b").
reqs = [r for r in os.environ.get("FAKE_PIP_REQUIRES", "").split(",") if r]
meta = Path(os.environ["FAKE_PIP_SITE"]) / "cortex_vec-0.0.0.dist-info" / "METADATA"
meta.write_text("Metadata-Version: 2.1\\nName: cortex-vec\\nVersion: 0.0.0\\n"
                + "".join(f"Requires-Dist: {r}\\n" for r in reqs))
"""


@dataclass
class Layout:
    root: Path
    site: Path
    plugin: Path
    home: Path
    fakepip: Path
    piplog: Path

    @property
    def state_file(self) -> Path:
        return self.home / ".cortex" / "cvec-sync" / "state.json"

    @property
    def bundled_pkg(self) -> Path:
        return self.plugin / "cortex-vec" / "src" / "cortex_vec"

    def env(self, mode: str = "copy", sleep: float = 0.0, with_site: bool = True,
            requires: str = "", front: Path | None = None) -> dict:
        """``front`` goes ahead of site/ on PYTHONPATH, as a source checkout would."""
        env = {**os.environ, "HOME": str(self.home),
               "FAKE_PIP_MODE": mode, "FAKE_PIP_SLEEP": str(sleep),
               "FAKE_PIP_LOG": str(self.piplog), "FAKE_PIP_SITE": str(self.site),
               "FAKE_PIP_REQUIRES": requires}
        paths = ([str(front)] if front else []) + ([str(self.site)] if with_site else [])
        env["PYTHONPATH"] = os.pathsep.join(paths + [str(self.fakepip)])
        return env

    def state(self) -> dict:
        return json.loads(self.state_file.read_text())

    def pip_calls(self) -> int:
        return len(self.piplog.read_text().splitlines()) if self.piplog.exists() else 0


def _write_pkg(pkg: Path, marker: str, needs_dep: bool = False) -> None:
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text(f"MARKER = {marker!r}\n")
    # needs_dep: the CLI imports a module nothing installs, as a copy that
    # added a dependency would after a --no-deps reinstall.
    (pkg / "cli.py").write_text(("import cvec_fakedep\n" if needs_dep else "") + _CLI)


def make_layout(tmp_path: Path, same: bool = False, editable: bool = False,
                bundled: bool = True, version: str = "9.9.9",
                needs_dep: bool = False) -> Layout:
    lay = Layout(root=tmp_path, site=tmp_path / "site", plugin=tmp_path / "plugin",
                 home=tmp_path / "home", fakepip=tmp_path / "fakepip",
                 piplog=tmp_path / "pip.log")
    _write_pkg(lay.site / "cortex_vec", "old")
    dist = lay.site / "cortex_vec-0.0.0.dist-info"
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: cortex-vec\nVersion: 0.0.0\n")
    if editable:
        (dist / "direct_url.json").write_text(json.dumps(
            {"url": "file:///src/cortex-vec", "dir_info": {"editable": True}}))
    (lay.plugin / ".claude-plugin").mkdir(parents=True)
    (lay.plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": version}))
    if bundled:
        _write_pkg(lay.bundled_pkg, "old" if same else "new", needs_dep=needs_dep)
    (lay.fakepip / "pip").mkdir(parents=True)
    (lay.fakepip / "pip" / "__init__.py").write_text("")
    (lay.fakepip / "pip" / "__main__.py").write_text(_FAKE_PIP)
    lay.home.mkdir()
    return lay


def check_cmd(lay: Layout, no_site: bool = False) -> list[str]:
    flags = ["-S"] if no_site else []
    return ["python3", *flags, str(HELPER), "check", "--plugin-root", str(lay.plugin)]


def run_check(lay: Layout, **env_kw) -> str:
    no_site = not env_kw.get("with_site", True)
    res = subprocess.run(check_cmd(lay, no_site=no_site), capture_output=True, text=True,
                         env=lay.env(**env_kw), timeout=20)
    assert res.returncode == 0, res.stderr
    return res.stdout


def wait_settled(lay: Layout, timeout: float = 15.0) -> dict:
    """Waits until the background worker has written its final state."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            st = lay.state()
            if st.get("status") != "running":
                return st
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        time.sleep(0.1)
    seen = lay.state_file.read_text() if lay.state_file.exists() else "no state file"
    raise AssertionError(f"worker never settled: {seen}")
