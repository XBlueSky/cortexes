"""Single-raw distill plan: coverage intervals, budget ledger, lifecycle.

Deterministic navigation state only — no semantic verdicts, no
auto-promote/auto-skip. State lives under $XDG_CACHE_HOME/cortex/
distill-plans/<source_sha256>.json with an active.json pointer enforcing
one active raw at a time. Atomic writes, user-only permissions,
fail-closed on corruption or identity drift.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from . import raw_source as rs
from .raw_page import CONTROL_RESERVE, PageError

STATE_SCHEMA_VERSION = 1


def plans_dir() -> Path:
    root = os.environ.get("XDG_CACHE_HOME")
    base = Path(root) if root else Path.home() / ".cache"
    return base / "cortex" / "distill-plans"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False))
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _state_path(source_sha256: str) -> Path:
    return plans_dir() / (source_sha256 + ".json")


def _active_path() -> Path:
    return plans_dir() / "active.json"


# --- interval helpers (half-open [lo, hi) over source chars) ----------------


def _merge(intervals: list, lo: int, hi: int) -> list:
    out = []
    for a, b in sorted(intervals + [[lo, hi]]):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _covered(intervals: list, lo: int, hi: int) -> bool:
    for a, b in intervals:
        if a <= lo and hi <= b:
            return True
    return False


def _uncovered(target: list, reviewed: list) -> list:
    out = []
    for lo, hi in target:
        pos = lo
        for a, b in reviewed:
            if b <= pos or a >= hi:
                continue
            if a > pos:
                out.append([pos, min(a, hi)])
            pos = max(pos, b)
            if pos >= hi:
                break
        if pos < hi:
            out.append([pos, hi])
    return out


# --- lifecycle ---------------------------------------------------------------


def _save(state: dict) -> None:
    state["updated"] = _now()
    _write_json(_state_path(state["identity"]["source_sha256"]), state)


def _load_state_file(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        # A dangling reference (active.json points at a state file that
        # teardown already removed) is a recoverable "no active plan", not a
        # corruption -- do not fabricate a .corrupt rename for a missing file.
        raise PageError("PLAN_NOT_ACTIVE", reason="state file missing",
                        state_file=str(path))
    except (OSError, ValueError):
        corrupt = path.with_name(path.name + ".corrupt")
        if path.exists():
            os.replace(path, corrupt)
        raise PageError("PLAN_STATE_CORRUPT", state_file=str(path),
                        kept=str(corrupt))
    if ("schema_version" in state
            and state["schema_version"] != STATE_SCHEMA_VERSION):
        raise PageError("SCHEMA_VERSION_MISMATCH",
                        found=state.get("schema_version"),
                        expected=STATE_SCHEMA_VERSION)
    return state


def _read_active() -> dict:
    p = _active_path()
    if not p.exists():
        raise PageError("PLAN_NOT_ACTIVE")
    return _load_state_file(p)


def start_plan(raw_path: str, page_budget: int, session_budget: int) -> dict:
    ident, text = rs.load(raw_path)
    active = _active_path()
    if active.exists():
        try:
            ptr = _load_state_file(active)
            existing = _load_state_file(plans_dir() / ptr["state_file"])
        except PageError as e:
            # Only a genuinely unusable pointer is recoverable: a dangling
            # reference (PLAN_NOT_ACTIVE) or an unreadable/corrupt state file
            # (PLAN_STATE_CORRUPT, already renamed to .corrupt). Identity drift
            # such as SCHEMA_VERSION_MISMATCH is a VALID plan and must stay
            # fail-closed -- never silently discard or overwrite it.
            if e.code not in ("PLAN_NOT_ACTIVE", "PLAN_STATE_CORRUPT"):
                raise
            if active.exists():
                os.remove(active)
            existing = None
        if existing is not None:
            if existing["identity"]["source_sha256"] != ident.source_sha256:
                raise PageError("ANOTHER_PLAN_ACTIVE",
                                active_plan_id=existing["plan_id"],
                                active_raw=existing["identity"]["raw_path"])
            existing["note"] = "already-active"
            return existing
    spans = rs.parse(text)
    semantic = [[s.char_start, s.char_end] for s in spans
                if s.kind in rs.SPAN_REVIEW_KINDS
                or s.kind in rs.PREVIEW_REVIEW_KINDS]
    ambiguous = [[s.char_start, s.char_end] for s in spans
                 if s.kind in ("ambiguous", "opaque")]
    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "plan_id": ident.source_sha256[:12],
        "identity": ident.to_json(),
        "page_budget": page_budget,
        "session_budget": session_budget,
        "session_seq": 1,
        "session_used_chars": 0,
        "map_next_index": 0,
        "span_count": len(spans),
        "semantic": semantic,
        "ambiguous": ambiguous,
        "reviewed": [],
        "evidence": [],
        "status": "active",
        "expected_outcome": None,
        "created": _now(),
        "updated": _now(),
    }
    _save(state)
    _write_json(_active_path(),
                {"plan_id": state["plan_id"],
                 "state_file": ident.source_sha256 + ".json"})
    return state


def _load_by_plan_id(plan_id: str) -> dict:
    ptr = _read_active()
    if ptr["plan_id"] != plan_id:
        raise PageError("PLAN_NOT_ACTIVE", active_plan_id=ptr["plan_id"])
    return _load_state_file(plans_dir() / ptr["state_file"])


def load_for_page(plan_id: str, raw_path: str):
    """Validate identity + status, reparse; returns (state, ident, text, spans)."""
    state = _load_by_plan_id(plan_id)
    if state["status"] == "sealed":
        raise PageError("PLAN_SEALED", plan_id=plan_id)
    ident, text = rs.load(raw_path)
    rec = state["identity"]
    if (ident.source_sha256 != rec["source_sha256"]
            or ident.file_sha256 != rec["file_sha256"]):
        raise PageError("RAW_CHANGED", plan_id=plan_id)
    if (ident.schema_version != rec["schema_version"]
            or ident.parser_version != rec["parser_version"]):
        raise PageError("SCHEMA_VERSION_MISMATCH")
    return state, ident, text, rs.parse(text)


def charge_and_save(state: dict, page_chars: int) -> None:
    budget = state["session_budget"] - CONTROL_RESERVE
    if state["session_used_chars"] + page_chars > budget:
        raise PageError(
            "BUDGET_EXHAUSTED", budget_status="continuation_required",
            session_used_chars=state["session_used_chars"],
            session_remaining_chars=max(
                0, budget - state["session_used_chars"]),
            resume="cortex-vec distill-plan resume --plan-id "
                   + state["plan_id"] + " --new-session")
    state["session_used_chars"] += page_chars
    _save(state)


def _check_reviewed_range(state: dict, lo: int, hi: int) -> None:
    # Fail closed: the no-insight gate trusts state["reviewed"], so an
    # out-of-bounds or inverted range must never silently widen coverage.
    cap = state["identity"]["char_count"]
    if not (0 <= lo < hi <= cap):
        raise PageError("CURSOR_MISMATCH",
                        reason="reviewed range out of bounds",
                        char_start=lo, char_end=hi, char_count=cap)


def mark_map_progress(state: dict, next_index: int,
                      auto_reviewed: list) -> None:
    if not (0 <= next_index <= state["span_count"]):
        raise PageError("CURSOR_MISMATCH", reason="map index out of range",
                        next_index=next_index, span_count=state["span_count"])
    for lo, hi in auto_reviewed:
        _check_reviewed_range(state, lo, hi)
        state["reviewed"] = _merge(state["reviewed"], lo, hi)
    state["map_next_index"] = max(state["map_next_index"], next_index)
    _save(state)


def mark_reviewed(state: dict, lo: int, hi: int) -> None:
    _check_reviewed_range(state, lo, hi)
    state["reviewed"] = _merge(state["reviewed"], lo, hi)
    _save(state)


def add_evidence(state: dict, lo: int, hi: int, label: str) -> None:
    if not (0 <= lo < hi <= state["identity"]["char_count"]):
        raise PageError("CURSOR_MISMATCH", reason="evidence range invalid")
    if not _covered(state["reviewed"], lo, hi):
        raise PageError("UNREVIEWED_AMBIGUOUS_RANGE",
                        reason="evidence range not yet reviewed",
                        char_start=lo, char_end=hi)
    state["evidence"].append(
        {"char_start": lo, "char_end": hi, "label": label or ""})
    _save(state)


def status_payload(state: dict) -> dict:
    map_done = state["map_next_index"] >= state["span_count"]
    un_sem = _uncovered(state["semantic"], state["reviewed"])
    un_amb = _uncovered(state["ambiguous"], state["reviewed"])
    sem_done = not un_sem
    budget = state["session_budget"] - CONTROL_RESERVE
    remaining = max(0, budget - state["session_used_chars"])
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "plan_id": state["plan_id"],
        "raw_path": state["identity"]["raw_path"],
        "status": state["status"],
        "session_seq": state["session_seq"],
        "map_coverage_complete": map_done,
        "semantic_review_coverage_complete": sem_done,
        "unreviewed_semantic_ranges": un_sem[:20],
        "unreviewed_semantic_count": len(un_sem),
        "unreviewed_ambiguous_ranges": un_amb[:20],
        "positive_candidate_allowed": state["status"] == "active",
        "no_insight_candidate_allowed": bool(
            map_done and sem_done and not un_amb
            and state["status"] == "active"),
        "evidence_count": len(state["evidence"]),
        "session_used_chars": state["session_used_chars"],
        "session_remaining_chars": remaining,
        "budget_status": ("continuation_required" if remaining == 0
                          else "ok"),
    }


def resume_plan(plan_id: str, new_session: bool) -> dict:
    state = _load_by_plan_id(plan_id)
    if state["status"] != "sealed":
        ident, _ = rs.load(state["identity"]["raw_path"])
        rec = state["identity"]
        if (ident.source_sha256 != rec["source_sha256"]
                or ident.file_sha256 != rec["file_sha256"]):
            raise PageError("RAW_CHANGED", plan_id=plan_id)
    if new_session:
        state["session_used_chars"] = 0
        state["session_seq"] += 1
        _save(state)
    return state


def seal_plan(state: dict, expected_outcome: str) -> None:
    allowed = ("new", "pending-merge", "skip-routine", "no-insight")
    if expected_outcome not in allowed:
        raise PageError("CURSOR_MISMATCH",
                        reason="unknown expected outcome",
                        allowed=list(allowed))
    if expected_outcome == "no-insight" \
            and not status_payload(state)["no_insight_candidate_allowed"]:
        raise PageError("NO_INSIGHT_COVERAGE_INCOMPLETE",
                        detail=status_payload(state))
    state["status"] = "sealed"
    state["expected_outcome"] = expected_outcome
    _save(state)


def complete_plan(plan_id: str, raw_path: str) -> dict:
    state = _load_by_plan_id(plan_id)
    if state["status"] != "sealed":
        raise PageError("PLAN_NOT_ACTIVE", reason="seal before complete")
    ident, _ = rs.load(raw_path)
    if ident.source_sha256 != state["identity"]["source_sha256"]:
        raise PageError("RAW_CHANGED", reason="source content changed")
    from .distill_queue import classify
    outcome = classify(raw_path).outcome
    if outcome != state["expected_outcome"]:
        raise PageError("RAW_CHANGED",
                        reason="marker does not match sealed expectation",
                        found=outcome, expected=state["expected_outcome"])
    # Remove the active pointer FIRST so a crash mid-teardown leaves at most an
    # orphan state file (harmless; shown by `list`, overwritten on next start)
    # and a clean PLAN_NOT_ACTIVE -- never a dangling pointer that wedges.
    ap = _active_path()
    if ap.exists():
        os.remove(ap)
    sf = _state_path(state["identity"]["source_sha256"])
    if sf.exists():
        os.remove(sf)
    return {"plan_id": plan_id, "completed": True, "outcome": outcome}


# --- CLI dispatch (called from cli.py, before the heavy store import) --------


def dispatch(args) -> None:
    try:
        _cli(args)
    except PageError as e:
        from .raw_page import emit_error
        emit_error(e.code, **e.detail)


def _cli(args) -> None:
    from .config import get_map_config
    from .raw_page import emit

    action = args.action
    if action == "start":
        if not args.path:
            raise PageError("PLAN_NOT_ACTIVE", reason="start needs a raw path")
        mc = get_map_config()
        state = start_plan(args.path,
                           args.page_budget or mc["page_budget"],
                           args.session_budget or mc["session_budget"])
        emit(status_payload(state))
    elif action == "status":
        emit(status_payload(_load_by_plan_id(args.plan_id)))
    elif action == "resume":
        emit(status_payload(resume_plan(args.plan_id,
                                        new_session=args.new_session)))
    elif action == "evidence-add":
        if args.char_start is None or args.char_end is None:
            raise PageError("CURSOR_MISMATCH",
                            reason="evidence-add requires --char-start "
                                   "and --char-end")
        state = _load_by_plan_id(args.plan_id)
        if state["status"] != "active":
            raise PageError("PLAN_SEALED", plan_id=args.plan_id)
        add_evidence(state, args.char_start, args.char_end, args.label)
        emit(status_payload(state))
    elif action == "seal":
        state = _load_by_plan_id(args.plan_id)
        seal_plan(state, args.expected_outcome)
        emit(status_payload(state))
    elif action == "complete":
        state = _load_by_plan_id(args.plan_id)
        emit(complete_plan(args.plan_id, state["identity"]["raw_path"]))
    elif action == "list":
        rows = []
        d = plans_dir()
        if d.is_dir():
            for p in sorted(d.glob("*.json")):
                if p.name == "active.json":
                    continue
                try:
                    s = _load_state_file(p)
                except PageError:
                    rows.append({"state_file": p.name,
                                 "status": "corrupt"})
                    continue
                rows.append({"plan_id": s["plan_id"],
                             "raw_path": s["identity"]["raw_path"],
                             "status": s["status"]})
        emit({"plans": rows})
    elif action == "clear":
        ap = _active_path()
        try:
            ptr = _read_active()  # pointer only; does not load the state file
        except PageError:
            ptr = None
        if ptr is None:
            raise PageError("PLAN_NOT_ACTIVE",
                            reason="no active plan to clear")
        if ptr.get("plan_id") != args.plan_id:
            raise PageError("PLAN_NOT_ACTIVE",
                            reason="plan-id does not match the active plan",
                            active_plan_id=ptr.get("plan_id"))
        # Remove the pointer first, then the state file if it still exists.
        if ap.exists():
            os.remove(ap)
        sf = plans_dir() / ptr["state_file"]
        if sf.exists():
            os.remove(sf)
        emit({"plan_id": args.plan_id, "cleared": True})
    else:
        raise PageError("PLAN_NOT_ACTIVE", reason="unknown action")
