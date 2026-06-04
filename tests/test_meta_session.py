"""Tests for meta_session.is_meta_session — detect cortex maintenance-pipeline
sessions so the SessionEnd hook can stamp them distilled and stop the vault
from re-feeding its own distill queue.

Run with: python3 -m unittest tests.test_meta_session
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

from meta_session import is_meta_session, main  # noqa: E402


def _skill_invocation(skill: str) -> str:
    return json.dumps({
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "Skill", "input": {"skill": skill, "args": ""}}
            ],
        },
    })


def _assistant_text(text: str) -> str:
    return json.dumps({
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    })


def _user_tool_result(text: str) -> str:
    return json.dumps({
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": text}
            ],
        },
    })


def _write_jsonl(lines: list[str]) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    )
    tmp.write("\n".join(lines) + "\n")
    tmp.close()
    return Path(tmp.name)


class IsMetaSession(unittest.TestCase):
    # --- positive: pure maintenance-pipeline sessions ---
    def test_distill_session_is_meta(self):
        p = _write_jsonl([
            _assistant_text("Let me distill the raw records."),
            _skill_invocation("cortex:distill"),
        ])
        self.assertTrue(is_meta_session(p))

    def test_weekly_session_is_meta(self):
        p = _write_jsonl([_skill_invocation("cortex:weekly")])
        self.assertTrue(is_meta_session(p))

    def test_broadcast_session_is_meta(self):
        p = _write_jsonl([_skill_invocation("cortex:broadcast")])
        self.assertTrue(is_meta_session(p))

    def test_genesis_session_is_meta(self):
        p = _write_jsonl([_skill_invocation("cortex:genesis")])
        self.assertTrue(is_meta_session(p))

    # The dominant real-world form is the double-prefix plugin:skill ID
    # (cortex:cortex-distill), not the slash-command alias (cortex:distill).
    def test_double_prefix_distill_is_meta(self):
        p = _write_jsonl([_skill_invocation("cortex:cortex-distill")])
        self.assertTrue(is_meta_session(p))

    def test_double_prefix_broadcast_is_meta(self):
        p = _write_jsonl([_skill_invocation("cortex:cortex-broadcast")])
        self.assertTrue(is_meta_session(p))

    def test_double_prefix_weekly_is_meta(self):
        p = _write_jsonl([_skill_invocation("cortex:cortex-weekly")])
        self.assertTrue(is_meta_session(p))

    def test_distill_and_broadcast_session_is_meta(self):
        # weekly/distill runs commonly invoke broadcast inline.
        p = _write_jsonl([
            _skill_invocation("cortex:cortex-distill"),
            _skill_invocation("cortex:cortex-broadcast"),
        ])
        self.assertTrue(is_meta_session(p))

    # --- negative: real work sessions that merely TOUCH cortex ---
    def test_query_session_not_meta(self):
        # cortex:query fires proactively inside normal work — must be recorded.
        p = _write_jsonl([
            _assistant_text("Checking prior notes."),
            _skill_invocation("cortex:query"),
            _assistant_text("Now back to the real task."),
        ])
        self.assertFalse(is_meta_session(p))

    def test_evolve_session_not_meta(self):
        # cortex:evolve saves one note during real work — the session has content.
        p = _write_jsonl([_skill_invocation("cortex:evolve")])
        self.assertFalse(is_meta_session(p))

    def test_using_cortex_not_meta(self):
        # auto-loaded every session; matching it would flag everything.
        p = _write_jsonl([_skill_invocation("cortex:using-cortex")])
        self.assertFalse(is_meta_session(p))

    def test_double_prefix_query_not_meta(self):
        # cortex:cortex-query is the common real form of a proactive query.
        p = _write_jsonl([
            _skill_invocation("cortex:cortex-query"),
            _skill_invocation("cortex:using-cortex"),
        ])
        self.assertFalse(is_meta_session(p))

    def test_double_prefix_evolve_not_meta(self):
        p = _write_jsonl([_skill_invocation("cortex:cortex-evolve")])
        self.assertFalse(is_meta_session(p))

    def test_plugin_dev_session_not_meta(self):
        # Editing the distill code mentions "cortex:distill" in text/results but
        # never INVOKES the skill — must stay recordable.
        p = _write_jsonl([
            _assistant_text("Editing the cortex:distill skill SKILL.md"),
            _user_tool_result("grep cortex:distill skills/cortex-distill/SKILL.md"),
            _skill_invocation("superpowers:test-driven-development"),
        ])
        self.assertFalse(is_meta_session(p))

    def test_plain_work_session_not_meta(self):
        p = _write_jsonl([
            _assistant_text("Fixing a bug."),
            _user_tool_result("all tests pass"),
        ])
        self.assertFalse(is_meta_session(p))

    # --- robustness ---
    def test_malformed_lines_skipped(self):
        p = _write_jsonl([
            "{not valid json",
            "",
            _skill_invocation("cortex:distill"),
            "garbage}",
        ])
        self.assertTrue(is_meta_session(p))

    def test_nonexistent_file_not_meta(self):
        self.assertFalse(is_meta_session(Path("/no/such/transcript.jsonl")))


class MainCli(unittest.TestCase):
    def test_exit_0_when_meta(self):
        p = _write_jsonl([_skill_invocation("cortex:distill")])
        self.assertEqual(main(["meta_session.py", str(p)]), 0)

    def test_exit_1_when_not_meta(self):
        p = _write_jsonl([_assistant_text("real work")])
        self.assertEqual(main(["meta_session.py", str(p)]), 1)

    def test_exit_2_on_usage_error(self):
        self.assertEqual(main(["meta_session.py"]), 2)


if __name__ == "__main__":
    unittest.main()
