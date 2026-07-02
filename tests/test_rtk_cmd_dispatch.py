"""find_mcp_filter routing — server-token matching, drift coverage."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

from rtk_cmd.dispatch import find_mcp_filter  # noqa: E402
from rtk_cmd.mcp_playwright import filter_playwright_tool  # noqa: E402
from rtk_cmd.mcp_tools import filter_mcp_tool  # noqa: E402


class FindMcpFilter(unittest.TestCase):
    def test_playwright_kaer_morhen_drift(self):
        self.assertIs(find_mcp_filter("mcp__plugin_kaer-morhen_playwright__browser_evaluate"),
                      filter_playwright_tool)

    def test_playwright_bare(self):
        self.assertIs(find_mcp_filter("mcp__playwright__browser_snapshot"),
                      filter_playwright_tool)

    def test_gitlab_still_routed(self):
        self.assertIs(find_mcp_filter("mcp__plugin_acme-corp-workflows_gitlab__get_merge_request"),
                      filter_mcp_tool)

    def test_zoekt_still_routed(self):
        self.assertIs(find_mcp_filter("mcp__zoekt__search"), filter_mcp_tool)

    def test_unrelated_returns_none(self):
        self.assertIsNone(find_mcp_filter("mcp__plugin_serena_serena__find_symbol"))
        self.assertIsNone(find_mcp_filter("mcp__context7__get_docs"))


if __name__ == "__main__":
    unittest.main()
