"""Trailer-anchored distill/broadcast queue detection.

The distilled marker is, by construction, a Raw file's LAST non-empty line.
A pipeline meta-session's body quotes the marker string dozens of times (it
printfs markers onto OTHER files), so any body-substring scan is fooled. These
tests pin the invariant: only the last non-empty line is authoritative.
"""

from cortex_vec import distill_queue as dq


def _write(tmp_path, rel, body):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


# --- classify(): the core invariant -----------------------------------------


def test_polluted_body_without_trailer_is_undistilled(tmp_path):
    # A pipeline meta-session: dozens of BARE whole-line markers appear in the
    # conversation body (captured printf output stamping OTHER files), then it
    # ends with normal prose and has NO real marker. Exactly what fooled grep.
    noise = "\n".join(
        f"<!-- distilled: 2026-06-1{i % 10} → (skip: routine) -->" for i in range(113)
    )
    body = (
        "---\ntype: session\n---\n\n### User\n\n跑 distill\n\n### Claude\n\n"
        f"{noise}\n\n結論:這場 meta-session 沒有要提煉的東西。\n"
    )
    p = _write(tmp_path, "Raw/2026/06/12/x_session_cortex.md", body)
    assert dq.classify(p).outcome == "undistilled"


def test_header_marker_before_conversation_is_distilled(tmp_path):
    # The dominant historical convention: distill writes the marker into the
    # header (before the first ### User turn), NOT at EOF. Body ends with /exit.
    body = (
        "---\ndate: 2026-05-04\ntime: 14:49:22\ntype: session\n---\n\n"
        "<!-- distilled: 2026-05-04 → (no insight) -->\n\n"
        "### User\n\nlots of real work\n\n### Claude\n\ndid stuff\n\n`/exit`\n"
    )
    p = _write(tmp_path, "Raw/2026/05/04/h_session_dsm.md", body)
    st = dq.classify(p)
    assert st.outcome == "no-insight"
    assert dq.is_distilled(st)


def test_header_pending_merge_with_merged_segment(tmp_path):
    body = (
        "---\ntype: session\n---\n"
        "<!-- distilled: 2026-05-18 → pending-merge: Projects/libdsm/x.md (0.46) "
        "| merged: 2026-05-18 → [[a]], [[b]] -->\n"
        "### User\nwork\n### Claude\nreply\n"
    )
    p = _write(tmp_path, "Raw/2026/05/18/h2_session_libdsm.md", body)
    st = dq.classify(p)
    assert st.outcome == "pending-merge"
    assert st.broadcast_resolved is True
    assert not dq.is_broadcast_eligible(st)


def test_marker_quoted_deep_in_conversation_is_undistilled(tmp_path):
    # A genuine work session that merely quotes one bare marker deep in the
    # conversation (not the last line, after ### User) → still undistilled.
    body = (
        "---\ntype: session\n---\n\n### User\n\nlook at distill\n\n### Claude\n\n"
        + "filler\n" * 50
        + "<!-- distilled: 2026-06-04 → (skip: routine) -->\n"
        + "more conversation after the quote, the session continues\n"
    )
    p = _write(tmp_path, "Raw/2026/06/04/q_session_kaer-morhen.md", body)
    assert dq.classify(p).outcome == "undistilled"


def test_skip_meta_session_trailer_is_distilled(tmp_path):
    body = (
        "body discussing `<!-- distilled:` markers a lot\n\n"
        "<!-- distilled: 2026-06-12 → (skip: meta-session) -->\n"
    )
    p = _write(tmp_path, "Raw/2026/06/12/m_session_cortex.md", body)
    st = dq.classify(p)
    assert st.outcome == "skip-meta"
    assert dq.is_distilled(st)


def test_new_outcome(tmp_path):
    p = _write(tmp_path, "Raw/a.md", "x\n<!-- distilled: 2026-06-10 → Notes/DSM/foo.md -->\n")
    st = dq.classify(p)
    assert st.outcome == "new"
    assert dq.is_broadcast_eligible(st)


def test_pending_merge_outcome(tmp_path):
    p = _write(
        tmp_path, "Raw/b.md",
        "x\n<!-- distilled: 2026-06-10 → pending-merge: Notes/X.md (0.52) -->\n",
    )
    st = dq.classify(p)
    assert st.outcome == "pending-merge"
    assert dq.is_broadcast_eligible(st)


def test_merged_segment_not_eligible(tmp_path):
    p = _write(
        tmp_path, "Raw/c.md",
        "x\n<!-- distilled: 2026-06-10 → pending-merge: Notes/X.md (0.52) "
        "| merged: 2026-06-11 → [[A]], [[B]] -->\n",
    )
    st = dq.classify(p)
    assert st.outcome == "pending-merge"
    assert st.broadcast_resolved is True
    assert not dq.is_broadcast_eligible(st)


def test_broadcast_segment_not_eligible(tmp_path):
    p = _write(
        tmp_path, "Raw/d.md",
        "x\n<!-- distilled: 2026-06-10 → Notes/X.md | broadcast: 2026-06-11 → [[A]] -->\n",
    )
    st = dq.classify(p)
    assert st.outcome == "new"
    assert not dq.is_broadcast_eligible(st)


def test_skip_routine(tmp_path):
    p = _write(tmp_path, "Raw/e.md", "x\n<!-- distilled: 2026-06-10 → (skip: routine) -->\n")
    st = dq.classify(p)
    assert st.outcome == "skip-routine"
    assert dq.is_distilled(st)
    assert not dq.is_broadcast_eligible(st)


def test_no_insight(tmp_path):
    p = _write(tmp_path, "Raw/f.md", "x\n<!-- distilled: 2026-06-10 → (no insight) -->\n")
    assert dq.classify(p).outcome == "no-insight"


def test_legacy_no_extractable_content(tmp_path):
    p = _write(
        tmp_path, "Raw/g.md",
        "x\n<!-- distilled: 2026-06-10 → (no extractable content) -->\n",
    )
    st = dq.classify(p)
    assert dq.is_distilled(st)
    assert not dq.is_broadcast_eligible(st)


def test_trailing_blank_lines_tolerated(tmp_path):
    p = _write(
        tmp_path, "Raw/h.md",
        "x\n<!-- distilled: 2026-06-10 → Notes/X.md -->\n\n\n   \n",
    )
    assert dq.classify(p).outcome == "new"


# --- queue builders ----------------------------------------------------------


def test_distill_queue_returns_only_undistilled_fifo(tmp_path):
    root = tmp_path / "Raw"
    _write(tmp_path, "Raw/2026/06/10/a.md", "body\n")  # undistilled
    _write(tmp_path, "Raw/2026/06/11/b.md",
           "body\n<!-- distilled: 2026-06-11 → (skip: meta-session) -->\n")  # done
    _write(tmp_path, "Raw/2026/06/12/c.md", "body\n")  # undistilled
    q = dq.distill_queue(root)
    assert [p.name for p in q] == ["a.md", "c.md"]  # FIFO by path, done excluded


def test_broadcast_queue_only_eligible(tmp_path):
    root = tmp_path / "Raw"
    _write(tmp_path, "Raw/01.md", "x\n<!-- distilled: 2026-06-10 → Notes/N.md -->\n")  # new → eligible
    _write(tmp_path, "Raw/02.md",
           "x\n<!-- distilled: 2026-06-10 → pending-merge: Notes/X.md (0.5) -->\n")  # eligible
    _write(tmp_path, "Raw/03.md", "x\n<!-- distilled: 2026-06-10 → (skip: routine) -->\n")  # no
    _write(tmp_path, "Raw/04.md",
           "x\n<!-- distilled: 2026-06-10 → Notes/N.md | broadcast: 2026-06-11 → (no changes) -->\n")  # done
    _write(tmp_path, "Raw/05.md", "body only, undistilled\n")  # not distilled
    q = dq.broadcast_queue(root)
    assert [p.name for p in q] == ["01.md", "02.md"]


# --- CLI dispatch glue -------------------------------------------------------


def test_dispatch_raw_state(tmp_path, capsys):
    p = _write(tmp_path, "Raw/m.md", "x\n<!-- distilled: 2026-06-12 → (skip: meta-session) -->\n")
    dq.dispatch_raw_state(str(p))
    assert "skip-meta" in capsys.readouterr().out


def test_dispatch_distill_queue(tmp_path, capsys):
    _write(tmp_path, "Raw/aa.md", "undistilled body\n")
    _write(tmp_path, "Raw/bb.md", "x\n<!-- distilled: 2026-06-10 → (skip: routine) -->\n")
    dq.dispatch_distill_queue(str(tmp_path / "Raw"))
    out = capsys.readouterr().out
    assert "aa.md" in out and "bb.md" not in out


def test_dispatch_distill_queue_stat_json(tmp_path, capsys):
    import json
    _write(tmp_path, "Raw/2026/06/10/a.md",
           "### Claude\n\nhi\n\n> [tool] **Bash**: `ls`\n```output\na\nb\n```\n")
    dq.dispatch_distill_queue(str(tmp_path / "Raw"), stat=True, as_json=True)
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["file"].endswith("a.md")
    assert rows[0]["raw"] > 0 and "chosen" in rows[0]
