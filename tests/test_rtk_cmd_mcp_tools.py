"""MCP tool filter tests (zoekt_search, docker_execute)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

from rtk_cmd.mcp_tools import (  # noqa: E402
    filter_docker_execute,
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


class DockerExecute(unittest.TestCase):
    def test_strips_ansi(self):
        raw = (
            "🐳 Docker Exec Results\n"
            "Status: ✅ Success\n\n"
            "📋 Output:\n"
            "\x1b[0;32m[==========] \x1b[mRunning 47 tests\n"
            "\x1b[0;32m[ RUN      ] \x1b[mSomeTest\n"
        )
        result = filter_docker_execute(raw)
        self.assertNotIn("\x1b", result)
        self.assertIn("Running 47 tests", result)
        self.assertIn("SomeTest", result)
        # emoji wrapper preserved
        self.assertIn("🐳 Docker Exec Results", result)

    def test_literal_bracket_ansi(self):
        # rtk transcripts sometimes capture the ANSI as literal text
        raw = "[0;32m[==========] [mRunning tests\n"
        result = filter_docker_execute(raw)
        self.assertNotIn("[0;32m", result)


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

    def test_docker_routed(self):
        raw = "\x1b[0;32mok\x1b[m\n"
        result = filter_mcp_tool(raw, "mcp__plugin_synology-dev-suite_syno-build-mcp__docker_execute")
        self.assertNotIn("\x1b", result)

    def test_build_project_passthrough(self):
        # build_project output is already well-shaped; we route the tool to
        # filter_mcp_tool but the function returns it unchanged.
        raw = "=== Build Result ===\nReturn Code: 0\n"
        result = filter_mcp_tool(raw, "mcp__plugin_synology-dev-suite_syno-build-mcp__build_project")
        self.assertEqual(result, raw)


if __name__ == "__main__":
    unittest.main()
