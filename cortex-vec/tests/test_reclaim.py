"""Reclaim of superseded Raw snapshots (one conversation recorded twice).

SessionEnd names each Raw by wall-clock, so a conversation that ends more than
once (`/clear`, exit + `--resume`) lands as several files whose bodies are
strict prefixes of the final one. These tests pin the rule that decides which
file is redundant — and, more importantly, which must never be touched: an
already-distilled Raw (a distilled marker stamped on it, a Note's `source:`
pointing back at it), a file longer than the survivor, and a file with no
conversation body at all.
"""
import subprocess
from types import SimpleNamespace

from cortex_vec import reclaim

FM = (
    "---\n"
    "date: {date}\n"
    "time: {time}\n"
    "type: session\n"
    "repo: {repo}\n"
    "tags: [session]\n"
    "---\n\n"
)


def _turns(n, seed):
    out = []
    for i in range(n):
        out.append(f"### User\n\n{seed} step {i}\n")
        out.append(f"### Claude\n\nhandled {seed} {i}\n")
    return "\n".join(out)


def _write(tmp_path, rel, *, turns=2, seed="work", date="2026-07-24",
           time="14:20:16", repo="acme-core", header_marker=None,
           trailer_marker=None, body=None):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    text = FM.format(date=date, time=time, repo=repo)
    if header_marker:
        text += f"{header_marker}\n\n"
    text += _turns(turns, seed) if body is None else body
    if trailer_marker:
        text += f"\n{trailer_marker}\n"
    p.write_text(text, encoding="utf-8")
    return p


# --- keep mode: the new Raw supersedes older snapshots of the same session ---


def test_older_prefix_snapshot_is_reclaimed(tmp_path):
    # Break: no prefix comparison (or one that compares whole files, including
    # the wall-clock frontmatter) → the redundant snapshot stays in the queue
    # and gets distilled as its own entry, spending the distill budget twice
    # on one conversation.
    small = _write(tmp_path, "Raw/2026/07/24/142016_session_acme-core.md",
                   turns=1, time="14:20:16")
    big = _write(tmp_path, "Raw/2026/07/24/145739_session_acme-core.md",
                 turns=3, time="14:57:39")

    assert reclaim.find_superseded(tmp_path / "Raw", keep=big) == [small]


def test_cross_day_resume_is_reclaimed(tmp_path):
    # Break: scoping the scan to "today" → the 4-day-old acme-web snapshot
    # (07/24 → 07/28 resume) is never recognised as superseded.
    small = _write(tmp_path, "Raw/2026/07/24/150626_session_acme-web.md",
                   turns=2, date="2026-07-24", repo="acme-web")
    big = _write(tmp_path, "Raw/2026/07/28/143130_session_acme-web.md",
                 turns=6, date="2026-07-28", repo="acme-web")

    assert reclaim.find_superseded(tmp_path / "Raw", keep=big) == [small]


def test_divergent_session_is_not_reclaimed(tmp_path):
    # Break: comparing only the first line / the turn count → an unrelated
    # session gets deleted.
    _write(tmp_path, "Raw/2026/07/24/142016_session_acme-core.md",
           turns=1, seed="unrelated")
    big = _write(tmp_path, "Raw/2026/07/24/145739_session_acme-core.md",
                 turns=3, seed="work")

    assert reclaim.find_superseded(tmp_path / "Raw", keep=big) == []


def test_candidate_longer_than_keep_is_not_reclaimed(tmp_path):
    # Break: comparing in the wrong direction → the LONGER, more complete Raw
    # is deleted and the truncated one survives. The catastrophic mutation.
    _write(tmp_path, "Raw/2026/07/24/142016_session_acme-core.md", turns=5)
    keep = _write(tmp_path, "Raw/2026/07/24/145739_session_acme-core.md", turns=2)

    assert reclaim.find_superseded(tmp_path / "Raw", keep=keep) == []


def test_distilled_snapshot_is_never_reclaimed(tmp_path):
    # Break: candidate set not restricted to the undistilled queue → a Raw
    # that already carries a distilled marker (and is referenced by a Note's
    # `source:`) is deleted, breaking that link.
    _write(tmp_path, "Raw/2026/07/24/142016_session_acme-core.md", turns=1,
           header_marker="<!-- distilled: 2026-07-25 → Notes/Tools/acme-core.md -->")
    big = _write(tmp_path, "Raw/2026/07/24/145739_session_acme-core.md", turns=3)

    assert reclaim.find_superseded(tmp_path / "Raw", keep=big) == []


def test_lone_raw_reclaims_nothing(tmp_path):
    # Break: the survivor prefix-matches itself → the file just written is
    # deleted immediately after landing.
    keep = _write(tmp_path, "Raw/2026/07/24/145739_session_acme-core.md", turns=3)

    assert reclaim.find_superseded(tmp_path / "Raw", keep=keep) == []


def test_body_less_snapshot_is_not_reclaimed(tmp_path):
    # Break: an empty body counts as a prefix of everything → every unrelated
    # frontmatter-only Raw in the queue is deleted on the next session end.
    _write(tmp_path, "Raw/2026/07/24/142016_session_acme-core.md",
           body="(filter failed)\n")
    big = _write(tmp_path, "Raw/2026/07/24/145739_session_acme-core.md", turns=3)

    assert reclaim.find_superseded(tmp_path / "Raw", keep=big) == []


def test_trailing_meta_marker_on_keep_does_not_block_match(tmp_path):
    # The hook stamps `(skip: meta-session)` onto the new Raw BEFORE reclaim
    # runs. Break: treating the marker line as body content that must also
    # appear in the candidate → reclaim silently stops working for every
    # pipeline session.
    small = _write(tmp_path, "Raw/2026/07/24/142016_session_cortex.md",
                   turns=1, repo="cortex")
    big = _write(tmp_path, "Raw/2026/07/24/145739_session_cortex.md",
                 turns=3, repo="cortex",
                 trailer_marker="<!-- distilled: 2026-07-24 → (skip: meta-session) -->")

    assert reclaim.find_superseded(tmp_path / "Raw", keep=big) == [small]


# --- backlog mode: pairwise over the whole queue -----------------------------


def test_backlog_mode_finds_superseded_across_conversations(tmp_path):
    a1 = _write(tmp_path, "Raw/2026/07/24/142016_session_acme-core.md",
                turns=1, seed="pkg")
    _write(tmp_path, "Raw/2026/07/24/145739_session_acme-core.md",
           turns=3, seed="pkg")
    b1 = _write(tmp_path, "Raw/2026/07/28/102504_session_acme-cli.md",
                turns=5, seed="tui", repo="acme-cli")
    _write(tmp_path, "Raw/2026/07/28/134826_session_acme-cli.md",
           turns=10, seed="tui", repo="acme-cli")

    assert reclaim.find_superseded(tmp_path / "Raw") == [a1, b1]


def test_two_identical_prefixes_and_one_longer_keep_the_longest(tmp_path):
    # The shape a real vault backlog actually had: two byte-identical 1-turn
    # snapshots plus the 3-turn recording that covers both. Reading the pair
    # alone it looks like each supersedes the other, so the tie-break must be
    # a total order — the maximum survives. Break: a tie-break that is not
    # (mtime, or dropping the path comparison) → either both identical copies
    # survive and the queue never shrinks, or the longest is flagged too and
    # the conversation is lost.
    a = _write(tmp_path, "Raw/2026/07/24/142016_session_acme-core.md", turns=1)
    b = _write(tmp_path, "Raw/2026/07/24/142201_session_acme-core.md", turns=1)
    _write(tmp_path, "Raw/2026/07/24/145739_session_acme-core.md", turns=3)

    assert reclaim.find_superseded(tmp_path / "Raw") == [a, b]


def test_identical_bodies_reclaim_exactly_one(tmp_path):
    # Break: mutual supersede → both copies are deleted and the conversation
    # is lost entirely.
    early = _write(tmp_path, "Raw/2026/07/24/142016_session_acme-core.md",
                   turns=2, time="14:20:16")
    _write(tmp_path, "Raw/2026/07/24/145739_session_acme-core.md",
           turns=2, time="14:57:39")

    assert reclaim.find_superseded(tmp_path / "Raw") == [early]


# --- apply: removal side effect ---------------------------------------------


def _git(repo, *argv):
    return subprocess.run(["git", "-C", str(repo), *argv],
                          capture_output=True, text=True, check=True).stdout


def test_apply_stages_deletion_in_the_vault_repo(tmp_path):
    # Break: unlinking without telling git → the vault's next auto-commit
    # leaves the deletion unstaged, so the removed snapshot silently returns
    # on the next checkout.
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    small = _write(tmp_path, "Raw/2026/07/24/142016_session_acme-core.md", turns=1)
    big = _write(tmp_path, "Raw/2026/07/24/145739_session_acme-core.md", turns=3)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "raw")

    removed = reclaim.apply_reclaim([small], vault=tmp_path)

    assert removed == [small]
    assert not small.exists()
    assert big.exists()
    assert "142016_session_acme-core.md" in _git(tmp_path, "diff", "--cached", "--name-only")


def test_apply_removes_untracked_snapshot(tmp_path):
    # Break: relying on `git rm` alone → with auto_commit off (nothing is
    # tracked) reclaim becomes a no-op and the queue never shrinks.
    small = _write(tmp_path, "Raw/2026/07/24/142016_session_acme-core.md", turns=1)

    removed = reclaim.apply_reclaim([small], vault=tmp_path)

    assert removed == [small]
    assert not small.exists()


# --- CLI dispatch -----------------------------------------------------------


def test_dispatch_lists_without_removing_by_default(tmp_path):
    small = _write(tmp_path, "Raw/2026/07/24/142016_session_acme-core.md", turns=1)
    big = _write(tmp_path, "Raw/2026/07/24/145739_session_acme-core.md", turns=3)

    reclaim.dispatch(SimpleNamespace(root=tmp_path / "Raw", keep=big,
                                     apply=False, vault=None))

    assert small.exists()


def test_dispatch_prints_removed_paths_with_apply(tmp_path, capsys):
    small = _write(tmp_path, "Raw/2026/07/24/142016_session_acme-core.md", turns=1)
    big = _write(tmp_path, "Raw/2026/07/24/145739_session_acme-core.md", turns=3)

    reclaim.dispatch(SimpleNamespace(root=tmp_path / "Raw", keep=big,
                                     apply=True, vault=tmp_path))

    assert capsys.readouterr().out.strip() == str(small)
    assert not small.exists()
