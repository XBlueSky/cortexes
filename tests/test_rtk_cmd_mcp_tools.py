"""MCP tool filter tests (zoekt_search, gitlab)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

from rtk_cmd.mcp_tools import (  # noqa: E402
    filter_gitlab_tool,
    filter_mcp_tool,
    filter_zoekt_search,
)


class ZoektSearch(unittest.TestCase):
    def _mk(self, files):
        total = sum(len(f.get("matches", [])) for f in files)
        return json.dumps({"success": True, "data": {"total_matches": total, "files": files}})

    def test_basic_flatten(self):
        raw = self._mk([
            {"repo": "org/a", "path": "src/x.py", "url": "https://long/url/hash",
             "branches": ["master"], "language": "Python",
             "matches": [{"line_number": 10, "line": "foo = 1"}]},
            {"repo": "org/b", "path": "y.js", "url": "https://long/url/hash2",
             "branches": ["master"], "language": "JavaScript",
             "matches": [{"line_number": 20, "line": "bar = 2"}]},
        ])
        result = filter_zoekt_search(raw)
        self.assertIn("zoekt: 2 matches in 2 files", result)
        self.assertIn("org/a", result)
        self.assertIn("src/x.py:10: foo = 1", result)
        self.assertIn("org/b", result)
        self.assertIn("y.js:20: bar = 2", result)
        # url/branches/language stripped
        self.assertNotIn("https://", result)
        self.assertNotIn("Python", result)
        self.assertNotIn("master", result)

    def test_groups_by_repo(self):
        raw = self._mk([
            {"repo": "org/a", "path": "f1.py", "matches": [{"line_number": 1, "line": "a"}]},
            {"repo": "org/a", "path": "f2.py", "matches": [{"line_number": 2, "line": "b"}]},
            {"repo": "org/b", "path": "f3.py", "matches": [{"line_number": 3, "line": "c"}]},
        ])
        result = filter_zoekt_search(raw)
        lines = result.splitlines()
        a_idx = [i for i, l in enumerate(lines) if l == "org/a"]
        b_idx = [i for i, l in enumerate(lines) if l == "org/b"]
        self.assertEqual(len(a_idx), 1, "org/a should only appear once")
        self.assertEqual(len(b_idx), 1)
        self.assertLess(a_idx[0], b_idx[0])

    def test_match_cap_per_file(self):
        many_matches = [{"line_number": i, "line": f"match {i}"} for i in range(15)]
        raw = self._mk([
            {"repo": "org/a", "path": "big.py", "matches": many_matches},
        ])
        result = filter_zoekt_search(raw)
        self.assertIn("... +5 more matches", result)
        # first 10 matches shown
        self.assertIn("big.py:0: match 0", result)
        self.assertIn("big.py:9: match 9", result)

    def test_truncates_long_lines(self):
        raw = self._mk([
            {"repo": "org/a", "path": "x.py",
             "matches": [{"line_number": 1, "line": "x" * 500}]},
        ])
        result = filter_zoekt_search(raw)
        # line preserved up to 200 chars + "…"
        self.assertIn("…", result)
        self.assertNotIn("x" * 300, result)

    def test_not_json_passthrough(self):
        txt = "zoekt: something non-JSON\n"
        self.assertEqual(filter_zoekt_search(txt), txt)

    def test_empty_results(self):
        raw = self._mk([])
        result = filter_zoekt_search(raw)
        self.assertIn("0 matches in 0 files", result)


_USER = {
    "username": "tonyhu",
    "id": "688",
    "name": "tonyhu",
    "avatar_url": "https://secure.gravatar.com/avatar/0000000000000000000000000000000000000000000000000000000000000000?s=80&d=identicon",
    "web_url": "https://git.example.com/tonyhu",
}
_REVIEWER = {
    "username": "reviewer1",
    "id": "9001",
    "name": "reviewer1",
    "avatar_url": "https://secure.gravatar.com/avatar/abc?s=80",
    "web_url": "https://git.example.com/reviewer1",
    "state": "active",
}


class GitlabTool(unittest.TestCase):
    def test_collapses_user_in_mr(self):
        mr = {
            "id": "304369",
            "iid": "21",
            "title": "feat(x): y",
            "description": "long body",
            "author": _USER,
            "assignees": [_REVIEWER],
            "reviewers": [_REVIEWER],
            "state": "opened",
            "web_url": "https://git.example.com/org/project/-/merge_requests/21",
        }
        result = filter_gitlab_tool(json.dumps(mr))
        parsed = json.loads(result)
        # user objects collapsed to "@username" strings
        self.assertEqual(parsed["author"], "@tonyhu")
        self.assertEqual(parsed["assignees"], ["@reviewer1"])
        self.assertEqual(parsed["reviewers"], ["@reviewer1"])
        # everything else preserved
        self.assertEqual(parsed["title"], "feat(x): y")
        self.assertEqual(parsed["description"], "long body")
        self.assertEqual(parsed["iid"], "21")
        self.assertEqual(parsed["state"], "opened")
        self.assertIn("merge_requests/21", parsed["web_url"])
        # noise gone from the nested objects
        self.assertNotIn("avatar_url", result)
        self.assertNotIn("gravatar", result)

    def test_collapses_user_in_list(self):
        mrs = [
            {"iid": str(i), "title": f"MR {i}", "author": _USER, "reviewers": [_REVIEWER]}
            for i in range(3)
        ]
        result = filter_gitlab_tool(json.dumps(mrs))
        parsed = json.loads(result)
        self.assertEqual(len(parsed), 3)
        for entry in parsed:
            self.assertEqual(entry["author"], "@tonyhu")
            self.assertEqual(entry["reviewers"], ["@reviewer1"])

    def test_collapses_user_in_notes(self):
        notes = [
            {
                "id": "3777240",
                "type": None,
                "body": "requested review from @reviewer1",
                "author": _USER,
                "created_at": "2026-05-25T18:34:49.602+08:00",
                "system": True,
                "noteable_id": "304369",
            }
        ]
        result = filter_gitlab_tool(json.dumps(notes))
        parsed = json.loads(result)
        self.assertEqual(parsed[0]["author"], "@tonyhu")
        self.assertEqual(parsed[0]["body"], "requested review from @reviewer1")

    def test_collapses_nested_approval(self):
        mr = {
            "iid": "21",
            "approval_summary": {
                "approved": True,
                "approved_by": [_REVIEWER],
                "approved_by_usernames": ["reviewer1"],
            },
        }
        result = filter_gitlab_tool(json.dumps(mr))
        parsed = json.loads(result)
        self.assertEqual(parsed["approval_summary"]["approved_by"], ["@reviewer1"])
        # parallel list preserved
        self.assertEqual(parsed["approval_summary"]["approved_by_usernames"], ["reviewer1"])

    def test_yields_byte_savings(self):
        raw = json.dumps([
            {"iid": str(i), "title": f"MR {i}", "description": "x" * 50,
             "author": _USER, "assignees": [_USER], "reviewers": [_REVIEWER]}
            for i in range(20)
        ])
        result = filter_gitlab_tool(raw)
        # 20 MRs × 3 user objects each × ~200 bytes of noise = serious savings
        self.assertLess(len(result), len(raw) // 2)

    def test_passthrough_on_invalid_json(self):
        raw = "Not JSON {{{ broken"
        self.assertEqual(filter_gitlab_tool(raw), raw)

    def test_passthrough_on_scalar_json(self):
        # An MR endpoint that legitimately returns a string/number shouldn't crash
        self.assertEqual(filter_gitlab_tool('"ok"'), '"ok"')
        self.assertEqual(filter_gitlab_tool("42"), "42")

    def test_non_user_dict_not_collapsed(self):
        # Something that happens to have a `username` key but is not a user
        # object (no avatar_url) must be left alone.
        node = {"username": "tonyhu", "type": "audit-entry", "ts": "2026-05-25"}
        result = filter_gitlab_tool(json.dumps(node))
        parsed = json.loads(result)
        self.assertEqual(parsed, node)


class Dispatch(unittest.TestCase):
    def test_zoekt_routed(self):
        raw = json.dumps({"success": True, "data": {"total_matches": 1, "files": [
            {"repo": "r", "path": "p.py", "matches": [{"line_number": 1, "line": "foo"}]}
        ]}})
        result = filter_mcp_tool(raw, "mcp__zoekt__search")
        self.assertIn("1 matches", result)

    def test_zoekt_plugin_prefix_routed(self):
        raw = json.dumps({"success": True, "data": {"total_matches": 1, "files": [
            {"repo": "r", "path": "p.py", "matches": [{"line_number": 1, "line": "foo"}]}
        ]}})
        result = filter_mcp_tool(raw, "mcp__plugin_zoekt-mcp__search")
        self.assertIn("1 matches", result)

    def test_gitlab_routed(self):
        raw = json.dumps({"iid": "21", "title": "x", "author": _USER})
        result = filter_mcp_tool(raw, "mcp__plugin_acme-corp-workflows_gitlab__get_merge_request")
        parsed = json.loads(result)
        self.assertEqual(parsed["author"], "@tonyhu")


if __name__ == "__main__":
    unittest.main()
