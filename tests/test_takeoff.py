import os
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


def _vault_repo(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    _git(vault, "init", "-q")
    repo = _make_repo(tmp_path / "work")
    env = {**os.environ, "CORTEX_VAULT_PATH": str(vault)}
    return vault, repo, env


def test_prepare_ensures_gitignore_creates_dir_and_prints_path(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    out = subprocess.run(
        ["bash", str(TAKEOFF), "prepare", str(repo)],
        capture_output=True, text=True, check=True, env=env,
    )
    assert out.stdout.strip() == str(vault / ".takeoff" / "myrepo.md")
    assert ".takeoff/" in (vault / ".gitignore").read_text().splitlines()
    assert (vault / ".takeoff").is_dir()
    ci = subprocess.run(
        ["git", "-C", str(vault), "check-ignore", ".takeoff/myrepo.md"],
        capture_output=True,
    )
    assert ci.returncode == 0


def test_prepare_is_idempotent(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    for _ in range(2):
        subprocess.run(["bash", str(TAKEOFF), "prepare", str(repo)],
                       capture_output=True, text=True, check=True, env=env)
    lines = (vault / ".gitignore").read_text().splitlines()
    assert lines.count(".takeoff/") == 1


def test_path_has_no_side_effects(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    out = subprocess.run(
        ["bash", str(TAKEOFF), "path", str(repo)],
        capture_output=True, text=True, check=True, env=env,
    )
    assert out.stdout.strip() == str(vault / ".takeoff" / "myrepo.md")
    assert not (vault / ".takeoff").exists()


def test_clear_removes_baton(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    baton = vault / ".takeoff" / "myrepo.md"
    baton.parent.mkdir(parents=True)
    baton.write_text("---\nsummary: x\n---\nbody\n")
    out = subprocess.run(["bash", str(TAKEOFF), "clear", str(repo)],
                         capture_output=True, text=True, check=True, env=env)
    assert not baton.exists()
    assert out.stdout.strip() == f"cleared {baton}"


def test_prepare_refuses_when_no_repo(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    _git(vault, "init", "-q")
    plain = tmp_path / "plain"
    plain.mkdir()
    env = {**os.environ, "CORTEX_VAULT_PATH": str(vault)}
    res = subprocess.run(["bash", str(TAKEOFF), "prepare", str(plain)],
                         capture_output=True, text=True, env=env)
    assert res.returncode == 2


def test_prepare_refuses_when_vault_not_git(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()  # exists but is NOT a git repo
    repo = _make_repo(tmp_path / "work")
    env = {**os.environ, "CORTEX_VAULT_PATH": str(vault)}
    res = subprocess.run(
        ["bash", str(TAKEOFF), "prepare", str(repo)],
        capture_output=True, text=True, env=env,
    )
    assert res.returncode == 3
