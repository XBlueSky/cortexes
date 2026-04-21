"""Playwright MCP filter tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

from rtk_cmd.mcp_playwright import (  # noqa: E402
    filter_browser_network_requests,
    filter_playwright_tool,
)


class BrowserNetworkRequests(unittest.TestCase):
    def test_strips_noisy_headers(self):
        raw = """### Result
[GET] https://example.com/api/items => [200]
  Request headers:
    user-agent: Mozilla/5.0 (very long UA)
    sec-ch-ua: "Chromium";v="146"
    sec-ch-ua-mobile: ?0
    sec-ch-ua-platform: "macOS"
    accept: application/json
    accept-language: en-US,en;q=0.9
    accept-encoding: gzip, deflate, br
    referer: https://example.com/
    cookie: session=abc123
    x-request-id: req-42
"""
        result = filter_browser_network_requests(raw)
        # request line preserved
        self.assertIn("[GET] https://example.com/api/items => [200]", result)
        # block label preserved because at least one header survived
        self.assertIn("Request headers:", result)
        # noisy headers gone
        self.assertNotIn("user-agent:", result)
        self.assertNotIn("sec-ch-ua", result)
        self.assertNotIn("cookie:", result)
        self.assertNotIn("accept-encoding:", result)
        # distinguishing header kept
        self.assertIn("x-request-id: req-42", result)

    def test_drops_block_when_all_noise(self):
        raw = """### Result
[GET] https://example.com/ => [200]
  Request headers:
    user-agent: Mozilla/5.0
    accept: */*
    referer: https://other.com
  Response headers:
    content-type: application/json
"""
        result = filter_browser_network_requests(raw)
        # Request headers block entirely dropped
        self.assertNotIn("Request headers:", result)
        # Response block survives because content-type is not noise
        self.assertIn("Response headers:", result)
        self.assertIn("content-type: application/json", result)

    def test_compression_ratio_on_real_shape(self):
        # Simulate 5 requests with typical header boilerplate
        single = """[GET] https://example.com/api/item{i} => [200]
  Request headers:
    sec-ch-ua-platform: "macOS"
    referer: https://example.com/
    x-requested-with: XMLHttpRequest
    user-agent: Mozilla/5.0 very long
    accept: application/json
    sec-ch-ua: "Chromium";v="146"
    sec-ch-ua-mobile: ?0
"""
        raw = "### Result\n" + "".join(single.replace("{i}", str(i)) for i in range(5))
        result = filter_browser_network_requests(raw)
        # After stripping all 7 of those headers are noise → block should drop
        self.assertLess(len(result), len(raw) // 2, f"Expected >50% shrink, got {len(result)}/{len(raw)}")


class Dispatch(unittest.TestCase):
    def test_network_requests_routed(self):
        raw = """### Result
[GET] https://x.com/ => [200]
  Request headers:
    user-agent: foo
    x-app-id: keep-me
"""
        result = filter_playwright_tool(raw, "mcp__playwright__browser_network_requests")
        self.assertNotIn("user-agent", result)
        self.assertIn("x-app-id", result)

    def test_other_tools_unchanged(self):
        raw = "### Page\n- Page URL: https://x.com/\n"
        self.assertEqual(
            filter_playwright_tool(raw, "mcp__playwright__browser_click"),
            raw,
        )


if __name__ == "__main__":
    unittest.main()
