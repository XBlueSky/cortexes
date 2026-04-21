"""Filter playwright MCP tool outputs.

Only `browser_network_requests` is compressed: each logged request carries
~20 lines of HTTP boilerplate (user-agent, sec-ch-ua-*, accept headers,
cookies) that are ~95% identical across the whole session. Stripping those
known-noisy headers preserves every distinguishing attribute
(method/URL/status, auth, request-id, custom app headers) while cutting
the per-request footprint from 20+ lines to 2–5.

Other playwright tool outputs (navigate/click/snapshot/evaluate/screenshot)
are left verbatim:

- `browser_snapshot` carries `[ref=eNN]` accessibility-tree IDs that Claude
  uses to target elements in subsequent tool calls. Stripping them would
  silently break chained interactions.
- `browser_evaluate` returns the JS evaluation result the user explicitly
  asked for — classic content, not log. Compressing the middle could drop
  exactly the value the user cares about.
- navigate/click/screenshot/tabs outputs are already <600 B.

No rtk attribution here — this is not a port; rtk's `playwright_cmd.rs`
filters the playwright CLI, which is a different output shape.
"""
from __future__ import annotations

# Request/response headers that are noise across a session. Lower-cased.
_NOISY_HEADERS = {
    "user-agent",
    "accept",
    "accept-language",
    "accept-encoding",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
    "sec-fetch-user",
    "upgrade-insecure-requests",
    "cache-control",
    "pragma",
    "dnt",
    "cookie",
    "set-cookie",
    "referer",
    "origin",
    "connection",
    "host",
    "priority",
    "x-requested-with",
}


def filter_browser_network_requests(output: str) -> str:
    """Compress a `browser_network_requests` tool_result.

    Input shape (Markdown):

        ### Result
        [GET] https://... => [200]
          Request headers:
            user-agent: ...
            sec-ch-ua: ...
            ...
          Response headers:
            ...

    Output: same structure but with noisy headers dropped. If a
    `Request headers:` block ends up empty, we remove the block label too.
    """
    lines = output.splitlines()
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Detect a headers-block start; we want to peek ahead to filter it.
        stripped = line.strip().lower()
        if stripped in ("request headers:", "response headers:"):
            block_header = line
            i += 1
            kept: list[str] = []
            # Collect indented header lines
            while i < len(lines):
                h = lines[i]
                # A header line is indented (>= 4 spaces) and contains ":".
                # Anything else ends the block.
                if h.startswith("    ") and ":" in h:
                    key = h.strip().split(":", 1)[0].lower()
                    if key not in _NOISY_HEADERS:
                        kept.append(h)
                    i += 1
                else:
                    break
            if kept:
                result.append(block_header)
                result.extend(kept)
            # else: drop the entire block (label included) when every header
            # inside was noise.
            continue
        result.append(line)
        i += 1
    return "\n".join(result)


def filter_playwright_tool(output: str, tool_name: str) -> str:
    """Dispatch by MCP tool name. Returns output unchanged if not handled."""
    if tool_name.endswith("browser_network_requests"):
        return filter_browser_network_requests(output)
    return output
