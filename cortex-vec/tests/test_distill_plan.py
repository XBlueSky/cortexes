"""Plan lifecycle: identity binding, coverage gates, budget ledger."""
import json

import pytest

from cortex_vec import distill_plan as dp
from cortex_vec import raw_page as rp


RAW = ("---\nrepo: cortex\n---\n"
       "### User\n\n請看這個 bug\n\n"
       "### Claude\n\nroot cause 在 src/x.py:12\n\n"
       "> [tool] **Bash**: `git log`\n"
       "```output\nabc123 fix\n```\n")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    raw = tmp_path / "raw.md"
    raw.write_text(RAW, encoding="utf-8")
    return raw


def test_start_status_roundtrip(env):
    st = dp.start_plan(str(env), 12000, 100000)
    payload = dp.status_payload(st)
    assert payload["map_coverage_complete"] is False
    assert payload["no_insight_candidate_allowed"] is False
    assert payload["positive_candidate_allowed"] is True
    assert payload["session_remaining_chars"] == 100000 - rp.CONTROL_RESERVE


def test_second_raw_blocked_while_active(env, tmp_path):
    dp.start_plan(str(env), 12000, 100000)
    other = tmp_path / "other.md"
    other.write_text("### User\n\nx\n", encoding="utf-8")
    with pytest.raises(rp.PageError) as e:
        dp.start_plan(str(other), 12000, 100000)
    assert e.value.code == "ANOTHER_PLAN_ACTIVE"


def test_raw_mutation_fails_closed(env):
    st = dp.start_plan(str(env), 12000, 100000)
    env.write_text(RAW + "\nEXTRA PROSE LINE\n", encoding="utf-8")
    with pytest.raises(rp.PageError) as e:
        dp.load_for_page(st["plan_id"], str(env))
    assert e.value.code == "RAW_CHANGED"


def test_budget_exhaustion_and_new_session_reset(env):
    st = dp.start_plan(str(env), 12000, 3000)
    dp.charge_and_save(st, 900)
    with pytest.raises(rp.PageError) as e:
        dp.charge_and_save(st, 90)  # 900+90 > 3000-2048=952
    assert e.value.code == "BUDGET_EXHAUSTED"
    st2 = dp.resume_plan(st["plan_id"], new_session=True)
    assert st2["session_used_chars"] == 0 and st2["session_seq"] == 2


def test_no_insight_gate_requires_full_review(env):
    st = dp.start_plan(str(env), 12000, 100000)
    # complete the map traversal without reviewing semantic spans
    dp.mark_map_progress(st, st["span_count"], auto_reviewed=[])
    assert dp.status_payload(st)["map_coverage_complete"] is True
    assert dp.status_payload(st)["no_insight_candidate_allowed"] is False
    for lo, hi in list(st["semantic"]) + list(st["ambiguous"]):
        dp.mark_reviewed(st, lo, hi)
    assert dp.status_payload(st)["no_insight_candidate_allowed"] is True


def test_evidence_requires_reviewed_range(env):
    st = dp.start_plan(str(env), 12000, 100000)
    lo, hi = st["semantic"][0]
    with pytest.raises(rp.PageError):
        dp.add_evidence(st, lo, hi, "premature")
    dp.mark_reviewed(st, lo, hi)
    dp.add_evidence(st, lo, hi, "root cause line")
    assert st["evidence"][0]["label"] == "root cause line"


def test_seal_blocks_pages_and_complete_accepts_marker_only(env):
    st = dp.start_plan(str(env), 12000, 100000)
    dp.mark_map_progress(st, st["span_count"], auto_reviewed=[])
    for lo, hi in list(st["semantic"]) + list(st["ambiguous"]):
        dp.mark_reviewed(st, lo, hi)
    dp.seal_plan(st, "no-insight")
    with pytest.raises(rp.PageError) as e:
        dp.load_for_page(st["plan_id"], str(env))
    assert e.value.code == "PLAN_SEALED"
    # expected anchored marker transition is the ONLY accepted file delta
    with open(env, "a", encoding="utf-8") as f:
        f.write("\n<!-- distilled: 2026-07-16 → (no insight) -->\n")
    dp.complete_plan(st["plan_id"], str(env))
    state_file = dp.plans_dir() / (st["identity"]["source_sha256"] + ".json")
    assert not state_file.exists()
    assert not (dp.plans_dir() / "active.json").exists()


def test_complete_rejects_wrong_marker(env):
    st = dp.start_plan(str(env), 12000, 100000)
    dp.mark_map_progress(st, st["span_count"], auto_reviewed=[])
    for lo, hi in list(st["semantic"]) + list(st["ambiguous"]):
        dp.mark_reviewed(st, lo, hi)
    dp.seal_plan(st, "no-insight")
    with open(env, "a", encoding="utf-8") as f:
        f.write("\n<!-- distilled: 2026-07-16 → Notes/X.md -->\n")
    with pytest.raises(rp.PageError) as e:
        dp.complete_plan(st["plan_id"], str(env))
    assert e.value.code == "RAW_CHANGED"


def test_corrupt_state_fails_closed(env):
    st = dp.start_plan(str(env), 12000, 100000)
    sf = dp.plans_dir() / (st["identity"]["source_sha256"] + ".json")
    sf.write_text("{not json", encoding="utf-8")
    with pytest.raises(rp.PageError) as e:
        dp.load_for_page(st["plan_id"], str(env))
    assert e.value.code == "PLAN_STATE_CORRUPT"


def test_mark_reviewed_rejects_out_of_bounds_range(env):
    st = dp.start_plan(str(env), 12000, 100000)
    cap = st["identity"]["char_count"]
    with pytest.raises(rp.PageError):
        dp.mark_reviewed(st, 0, cap + 1)      # hi beyond end of source
    with pytest.raises(rp.PageError):
        dp.mark_reviewed(st, 5, 5)            # empty / inverted range
    # an over-broad range must NOT be able to spoof the no-insight gate
    assert dp.status_payload(st)["no_insight_candidate_allowed"] is False


def test_cli_dispatch_full_cycle(env, capsys):
    class A:
        def __init__(self, **kw):
            defaults = dict(path=None, plan_id=None, page_budget=None,
                            session_budget=None, char_start=None,
                            char_end=None, label="", expected_outcome=None,
                            new_session=False)
            defaults.update(kw)
            self.__dict__.update(defaults)

    dp.dispatch(A(action="start", path=str(env)))
    started = json.loads(capsys.readouterr().out)
    pid = started["plan_id"]
    dp.dispatch(A(action="status", plan_id=pid))
    assert json.loads(capsys.readouterr().out)["status"] == "active"
    dp.dispatch(A(action="clear", plan_id=pid))
    assert json.loads(capsys.readouterr().out)["cleared"] is True


def test_cli_start_without_path_errors(env, capsys):
    class A:
        action = "start"
        path = None
        page_budget = session_budget = None
    with pytest.raises(SystemExit):
        dp.dispatch(A())
    assert "error" in json.loads(capsys.readouterr().out)


def test_cli_evidence_add_missing_range_errors(env, capsys):
    class A:
        def __init__(self, **kw):
            d = dict(path=None, plan_id=None, page_budget=None,
                     session_budget=None, char_start=None, char_end=None,
                     label="", expected_outcome=None, new_session=False)
            d.update(kw)
            self.__dict__.update(d)

    dp.dispatch(A(action="start", path=str(env)))
    pid = json.loads(capsys.readouterr().out)["plan_id"]
    with pytest.raises(SystemExit):
        dp.dispatch(A(action="evidence-add", plan_id=pid))  # no char range
    out = capsys.readouterr().out
    assert json.loads(out)["error"] == "CURSOR_MISMATCH"


def test_dangling_active_pointer_recovers(env):
    # Simulate a crash during teardown that left active.json pointing at a
    # state file that no longer exists. The workflow must NOT wedge on
    # PLAN_STATE_CORRUPT: _load_by_plan_id surfaces a recoverable
    # PLAN_NOT_ACTIVE, and start creates a fresh plan for the same Raw.
    st = dp.start_plan(str(env), 12000, 100000)
    sf = dp.plans_dir() / (st["identity"]["source_sha256"] + ".json")
    sf.unlink()  # state file gone; active.json still points at it

    with pytest.raises(rp.PageError) as e:
        dp._load_by_plan_id(st["plan_id"])
    assert e.value.code == "PLAN_NOT_ACTIVE"

    st2 = dp.start_plan(str(env), 12000, 100000)
    assert st2["plan_id"] == st["plan_id"]
    assert st2.get("note") != "already-active"


def test_start_does_not_discard_valid_plan_on_schema_mismatch(env):
    # A valid, present active-plan state file created under a DIFFERENT schema
    # version is identity drift, not a dangling/corrupt pointer. start_plan on
    # the same Raw must fail closed (SCHEMA_VERSION_MISMATCH), NOT silently
    # discard/overwrite the recorded progress.
    st = dp.start_plan(str(env), 12000, 100000)
    lo, hi = st["semantic"][0]
    dp.mark_reviewed(st, lo, hi)
    sf = dp.plans_dir() / (st["identity"]["source_sha256"] + ".json")
    data = json.loads(sf.read_text())
    data["schema_version"] = 999
    sf.write_text(json.dumps(data))

    with pytest.raises(rp.PageError) as e:
        dp.start_plan(str(env), 12000, 100000)
    assert e.value.code == "SCHEMA_VERSION_MISMATCH"
    # state file preserved (not overwritten with a fresh reviewed=[] plan)
    after = json.loads(sf.read_text())
    assert after["schema_version"] == 999
    assert after["reviewed"] == [[lo, hi]]
