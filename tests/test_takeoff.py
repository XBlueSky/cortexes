import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SLUGLIB = REPO_ROOT / "hooks" / "scripts" / "lib" / "repo-slug.sh"
TAKEOFF = REPO_ROOT / "hooks" / "scripts" / "takeoff.sh"
INJECT = REPO_ROOT / "hooks" / "scripts" / "session-start-inject.sh"


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _make_repo(path, origin="https://example.com/acme/myrepo.git"):
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "remote", "add", "origin", origin)
    return path


def test_repo_slug_is_origin_basename_without_dotgit(tmp_path):
    repo = _make_repo(tmp_path / "work")
    out = subprocess.run(
        ["bash", "-c", f'source "{SLUGLIB}"; cortex_repo_slug "{repo}"'],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == "myrepo"


def test_repo_slug_empty_when_no_origin(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q")
    out = subprocess.run(
        ["bash", "-c", f'source "{SLUGLIB}"; cortex_repo_slug "{work}" || true'],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == ""
