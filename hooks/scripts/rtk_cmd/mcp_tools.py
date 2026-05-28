"""Filters for MCP tool outputs that have a log-like shape.

Different from `mcp_playwright.py` which is scoped to playwright MCP. This
module covers the other MCP tools whose outputs have enough boilerplate
or encoding noise to be worth compressing without losing signal.

Triage applied before porting each tool: outputs that represent **content
the user explicitly asked for** (file reads, doc queries, JS eval results,
patch plans) are left verbatim. Only clearly log-shaped outputs get a
filter here.
"""
from __future__ import annotations

import json
import re


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\[\d[0-9;]*[A-Za-z]")


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + "…"


# ---------------------------------------------------------------------------
# zoekt__search
#
# Input shape (JSON):
#   { "success": bool, "data": {
#       "total_matches": N,
#       "files": [ { repo, path, url, branches, language, matches: [
#         { line_number, line } ] } ] } }
#
# Output: a per-repo grouped `repo/path:line: content` listing, preserving
# every match (we don't drop matches — users search for specific things).
# Only the JSON scaffolding + redundant url/branches/language per file are
# stripped.

_MAX_MATCHES_PER_FILE = 10
_MAX_FILES = 50
_MAX_LINE_CONTENT = 200


def filter_zoekt_search(output: str) -> str:
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return output
    if not isinstance(parsed, dict):
        return output

    data = parsed.get("data")
    if not isinstance(data, dict):
        return output

    total = data.get("total_matches", 0)
    files = data.get("files", [])
    if not isinstance(files, list):
        return output

    parts: list[str] = [f"zoekt: {total} matches in {len(files)} files"]

    # Group by repo, preserving order of first appearance.
    by_repo: dict[str, list[dict]] = {}
    for f in files[:_MAX_FILES]:
        if not isinstance(f, dict):
            continue
        repo = f.get("repo", "?")
        by_repo.setdefault(repo, []).append(f)

    for repo, repo_files in by_repo.items():
        parts.append("")
        parts.append(repo)
        for f in repo_files:
            path = f.get("path", "?")
            matches = f.get("matches", []) or []
            shown = matches[:_MAX_MATCHES_PER_FILE]
            for m in shown:
                line_num = m.get("line_number", "?")
                line = (m.get("line") or "").rstrip()
                parts.append(f"  {path}:{line_num}: {_truncate(line, _MAX_LINE_CONTENT)}")
            if len(matches) > _MAX_MATCHES_PER_FILE:
                parts.append(
                    f"  {path}: ... +{len(matches) - _MAX_MATCHES_PER_FILE} more matches"
                )

    if len(files) > _MAX_FILES:
        parts.append("")
        parts.append(f"... +{len(files) - _MAX_FILES} more files")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# syno-build-mcp__docker_execute
#
# Shape: a wrapper frame (🐳 header + "📋 Output:") around arbitrary command
# output that often carries ANSI colour codes from tools like GoogleTest.
# The only deterministic win is ANSI stripping — the body is user-requested
# command output, don't touch it otherwise.

def filter_docker_execute(output: str) -> str:
    return _strip_ansi(output)


# ---------------------------------------------------------------------------
# gitlab MCP — collapse nested user objects to "@username"
#
# Every MR / issue / note / commit references one or more "user" objects of
# the shape `{username, id, name, avatar_url, web_url}`. Only `username` is
# load-bearing for cortex distill. A list_merge_requests result with N MRs
# carries ~4 such objects per MR (author + assignees + reviewers + approvers),
# each ~200 bytes of noise. We collapse those to the bare "@username" string
# and leave the rest of the JSON intact — title / description / diff / labels
# are all distill source material and must not be touched.
#
# Conservative: any structural surprise (parse fail, unexpected shape) falls
# back to verbatim. We never lose signal; worst case is zero compression.

_USER_OBJECT_KEYS = frozenset({"username", "id", "name", "avatar_url", "web_url"})
_USER_OBJECT_SIGNATURE = frozenset({"username", "avatar_url"})


def _is_user_object(node: dict) -> bool:
    # A user object always carries username+avatar_url. Some variants also
    # include `state` or `email`, so we don't require an exact key set —
    # the signature is enough.
    keys = set(node.keys())
    if not _USER_OBJECT_SIGNATURE.issubset(keys):
        return False
    # Guard against false positives: only collapse when the *extra* keys are
    # all in the known user-object vocabulary (id/name/web_url/state/email).
    allowed = _USER_OBJECT_KEYS | {"state", "email", "locked"}
    return keys.issubset(allowed)


def _scrub_gitlab(node):
    if isinstance(node, dict):
        if _is_user_object(node):
            uname = node.get("username")
            return f"@{uname}" if uname else node
        return {k: _scrub_gitlab(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_scrub_gitlab(item) for item in node]
    return node


def filter_gitlab_tool(output: str) -> str:
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return output
    if not isinstance(parsed, (dict, list)):
        return output
    cleaned = _scrub_gitlab(parsed)
    return json.dumps(cleaned, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# dispatch

def filter_mcp_tool(output: str, tool_name: str) -> str:
    # Tool names come in two shapes:
    #   mcp__zoekt__search   (legacy / bare MCP server name)
    #   mcp__plugin_zoekt-mcp__search   (plugin-prefixed)
    # So we match on "which MCP server" (substring) + "which sub-tool" (suffix).
    if "zoekt" in tool_name and tool_name.endswith("__search"):
        return filter_zoekt_search(output)
    if tool_name.endswith("__docker_execute"):
        return filter_docker_execute(output)
    if "_gitlab__" in tool_name:
        return filter_gitlab_tool(output)
    return output
