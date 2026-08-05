import json
import os
import subprocess
import time
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
    _git(vault, "config", "user.email", "cortex-test@example.com")
    _git(vault, "config", "user.name", "cortex test")
    repo = _make_repo(tmp_path / "work")
    env = {**os.environ, "CORTEX_VAULT_PATH": str(vault)}
    return vault, repo, env


def test_prepare_ensures_gitignore_creates_dir_and_prints_path(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    out = subprocess.run(
        ["bash", str(TAKEOFF), "prepare", str(repo), "my-line"],
        capture_output=True, text=True, check=True, env=env,
    )
    lines = out.stdout.strip().splitlines()
    assert lines[0] == str(vault / ".takeoff" / "myrepo" / "my-line.md")
    assert lines[1] == os.path.realpath(str(repo))
    assert ".takeoff/" in (vault / ".gitignore").read_text().splitlines()
    assert (vault / ".takeoff" / "myrepo").is_dir()


def test_prepare_missing_topic_exits_64(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    res = subprocess.run(["bash", str(TAKEOFF), "prepare", str(repo)],
                         capture_output=True, text=True, env=env)
    assert res.returncode == 64


def test_prepare_checkignore_covers_subdir_and_trash(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    subprocess.run(["bash", str(TAKEOFF), "prepare", str(repo), "my-line"],
                   capture_output=True, text=True, check=True, env=env)
    # Pin the RECURSIVE ignore: a future '.takeoff/*.md'-style rule must fail here.
    for rel in (".takeoff/myrepo/my-line.md", ".takeoff/.trash/myrepo/x-1.md"):
        ci = subprocess.run(["git", "-C", str(vault), "check-ignore", rel],
                            capture_output=True)
        assert ci.returncode == 0, rel


def test_prepare_is_idempotent(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    for _ in range(2):
        subprocess.run(["bash", str(TAKEOFF), "prepare", str(repo), "my-line"],
                       capture_output=True, text=True, check=True, env=env)
    lines = (vault / ".gitignore").read_text().splitlines()
    assert lines.count(".takeoff/") == 1


def test_missing_cwd_exits_64(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    for sub in ("path", "prepare", "clear"):
        res = subprocess.run(["bash", str(TAKEOFF), sub],
                             capture_output=True, text=True, env=env)
        assert res.returncode == 64, sub


def test_path_requires_valid_topic(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    for bad in ("", "Foo", "a b", "-x", "has_underscore",
                "resume", "done", "legacy", "a" * 65):
        res = subprocess.run(["bash", str(TAKEOFF), "path", str(repo), bad],
                             capture_output=True, text=True, env=env)
        assert res.returncode == 64, bad


def test_path_has_no_side_effects(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    out = subprocess.run(
        ["bash", str(TAKEOFF), "path", str(repo), "my-line"],
        capture_output=True, text=True, check=True, env=env,
    )
    assert out.stdout.strip() == str(vault / ".takeoff" / "myrepo" / "my-line.md")
    assert not (vault / ".takeoff").exists()


def _write_baton(vault, slug, topic, summary="s", workdir=None, legacy=False):
    if legacy:
        p = vault / ".takeoff" / f"{slug}.md"
    else:
        p = vault / ".takeoff" / slug / f"{topic}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = [f"repo: {slug}"]
    if not legacy:
        fm.append(f"topic: {topic}")
    if workdir is not None:
        fm.append(f"workdir: {workdir}")
    fm.append(f"summary: {summary}")
    p.write_text("---\n" + "\n".join(fm) + "\n---\nbody\n")
    return p


def test_clear_moves_to_trash_content_intact(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    baton = _write_baton(vault, "myrepo", "my-line",
                         workdir=os.path.realpath(str(repo)))
    content = baton.read_text()
    out = subprocess.run(["bash", str(TAKEOFF), "clear", str(repo), "my-line"],
                         capture_output=True, text=True, check=True, env=env)
    assert not baton.exists()
    trashed = list((vault / ".takeoff" / ".trash" / "myrepo").glob("my-line-*.md"))
    assert len(trashed) == 1
    assert trashed[0].read_text() == content
    assert out.stdout.startswith(f"trashed {baton} -> ")


def test_clear_workdir_mismatch_refuses(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    baton = _write_baton(vault, "myrepo", "my-line", workdir="/somewhere/else")
    res = subprocess.run(["bash", str(TAKEOFF), "clear", str(repo), "my-line"],
                         capture_output=True, text=True, env=env)
    assert res.returncode == 4
    assert baton.exists()
    assert "/somewhere/else" in res.stderr
    assert os.path.realpath(str(repo)) in res.stderr


def test_clear_force_overrides_workdir_mismatch(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    baton = _write_baton(vault, "myrepo", "my-line", workdir="/somewhere/else")
    subprocess.run(["bash", str(TAKEOFF), "clear", str(repo), "my-line", "--force"],
                   capture_output=True, text=True, check=True, env=env)
    assert not baton.exists()
    assert list((vault / ".takeoff" / ".trash" / "myrepo").glob("my-line-*.md"))


def test_clear_legacy_flag(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    baton = _write_baton(vault, "myrepo", None, legacy=True)  # no workdir field
    res = subprocess.run(["bash", str(TAKEOFF), "clear", str(repo), "--legacy"],
                         capture_output=True, text=True, check=True, env=env)
    assert not baton.exists()
    assert list((vault / ".takeoff" / ".trash" / "myrepo").glob("legacy-*.md"))
    assert "no workdir field" in res.stderr  # skip-with-warning path


def test_clear_missing_target_exits_64(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    res = subprocess.run(["bash", str(TAKEOFF), "clear", str(repo)],
                         capture_output=True, text=True, env=env)
    assert res.returncode == 64


def test_trash_prune_removes_old_files(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    trash = vault / ".takeoff" / ".trash" / "myrepo"
    trash.mkdir(parents=True)
    old = trash / "dead-line-20260601T000000.md"
    old.write_text("x")
    stamp = time.time() - 40 * 86400
    os.utime(old, (stamp, stamp))
    fresh = trash / "live-line-20260805T000000.md"
    fresh.write_text("y")
    subprocess.run(["bash", str(TAKEOFF), "prepare", str(repo), "any-line"],
                   capture_output=True, text=True, check=True, env=env)
    assert not old.exists()
    assert fresh.exists()


def test_clear_nonexistent_baton_exits_5(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    res = subprocess.run(["bash", str(TAKEOFF), "clear", str(repo), "no-such"],
                         capture_output=True, text=True, env=env)
    assert res.returncode == 5


def test_list_empty_outputs_nothing(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    out = subprocess.run(["bash", str(TAKEOFF), "list", str(repo)],
                         capture_output=True, text=True, check=True, env=env)
    assert out.stdout == ""


def test_list_multi_and_legacy_sorted_by_mtime(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    a = _write_baton(vault, "myrepo", "line-a", summary="oldest line")
    leg = _write_baton(vault, "myrepo", None, summary="middle legacy", legacy=True)
    b = _write_baton(vault, "myrepo", "line-b", summary="newest line")
    now = time.time()
    os.utime(a, (now - 300, now - 300))
    os.utime(leg, (now - 200, now - 200))
    os.utime(b, (now - 100, now - 100))
    out = subprocess.run(["bash", str(TAKEOFF), "list", str(repo)],
                         capture_output=True, text=True, check=True, env=env)
    rows = [line.split("\t") for line in out.stdout.strip().splitlines()]
    assert rows == [
        ["line-b", "newest line", str(b)],
        ["legacy", "middle legacy", str(leg)],
        ["line-a", "oldest line", str(a)],
    ]


def test_prepare_refuses_when_no_repo(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    _git(vault, "init", "-q")
    plain = tmp_path / "plain"
    plain.mkdir()
    env = {**os.environ, "CORTEX_VAULT_PATH": str(vault)}
    res = subprocess.run(["bash", str(TAKEOFF), "prepare", str(plain), "my-line"],
                         capture_output=True, text=True, env=env)
    assert res.returncode == 2


def test_prepare_refuses_when_vault_not_git(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()  # exists but is NOT a git repo
    repo = _make_repo(tmp_path / "work")
    env = {**os.environ, "CORTEX_VAULT_PATH": str(vault)}
    res = subprocess.run(
        ["bash", str(TAKEOFF), "prepare", str(repo), "my-line"],
        capture_output=True, text=True, env=env,
    )
    assert res.returncode == 3


def _run_inject(cwd, vault):
    env = {**os.environ, "CORTEX_VAULT_PATH": str(vault)}
    res = subprocess.run(["bash", str(INJECT)],
                         input=json.dumps({"cwd": str(cwd)}),
                         capture_output=True, text=True, env=env)
    assert res.returncode == 0, res.stderr
    if not res.stdout.strip():
        return ""
    return json.loads(res.stdout)["hookSpecificOutput"]["additionalContext"]


def test_inject_surfaces_pending_baton(tmp_path):
    vault = tmp_path / "vault"
    (vault / ".takeoff").mkdir(parents=True)
    (vault / ".takeoff" / "myrepo.md").write_text(
        "---\nrepo: myrepo\ncreated: 2026-06-30T00:00:00\n"
        "summary: 接續 refactor X 的第 3 步\n---\nbody\n"
    )
    repo = _make_repo(tmp_path / "work")
    ctx = _run_inject(repo, vault)
    assert "5. 載入交接［legacy］：接續 refactor X 的第 3 步" in ctx


def test_inject_no_baton_omits_takeoff_line(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    repo = _make_repo(tmp_path / "work")
    ctx = _run_inject(repo, vault)
    assert "載入交接" not in ctx
    assert "直接開始工作" in ctx  # regression: base menu still built


def test_inject_multi_batons_numbered_from_5(tmp_path):
    vault = tmp_path / "vault"
    repo = _make_repo(tmp_path / "work")
    older = _write_baton(vault, "myrepo", "old-line", summary="older work")
    newer = _write_baton(vault, "myrepo", "new-line", summary="newer work")
    now = time.time()
    os.utime(older, (now - 300, now - 300))
    os.utime(newer, (now - 100, now - 100))
    ctx = _run_inject(repo, vault)
    assert "5. 載入交接［new-line］：newer work" in ctx
    assert "6. 載入交接［old-line］：older work" in ctx


def test_inject_workdir_marker_only_when_foreign(tmp_path):
    vault = tmp_path / "vault"
    repo = _make_repo(tmp_path / "work")
    _write_baton(vault, "myrepo", "mine", summary="local line",
                 workdir=os.path.realpath(str(repo)))
    _write_baton(vault, "myrepo", "theirs", summary="foreign line",
                 workdir="/somewhere/else")
    ctx = _run_inject(repo, vault)
    assert "載入交接［theirs］：foreign line（來自 /somewhere/else）" in ctx
    assert "（來自 " + os.path.realpath(str(repo)) not in ctx


def test_inject_legacy_and_new_coexist(tmp_path):
    vault = tmp_path / "vault"
    repo = _make_repo(tmp_path / "work")
    _write_baton(vault, "myrepo", None, summary="old era", legacy=True)
    _write_baton(vault, "myrepo", "new-line", summary="new era")
    ctx = _run_inject(repo, vault)
    assert "載入交接［legacy］：old era" in ctx
    assert "載入交接［new-line］：new era" in ctx


def test_prepare_commits_gitignore_rule(tmp_path):
    vault, repo, env = _vault_repo(tmp_path)
    subprocess.run(
        ["bash", str(TAKEOFF), "prepare", str(repo), "my-line"],
        capture_output=True, text=True, check=True, env=env,
    )
    # The .gitignore change is committed, not left dirty in the working tree.
    status = subprocess.run(
        ["git", "-C", str(vault), "status", "--porcelain", ".gitignore"],
        capture_output=True, text=True, check=True,
    )
    assert status.stdout.strip() == ""
    # The latest commit touches .gitignore.
    log = subprocess.run(
        ["git", "-C", str(vault), "log", "-1", "--name-only", "--format=%s"],
        capture_output=True, text=True, check=True,
    )
    assert ".gitignore" in log.stdout
