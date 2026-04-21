"""Dispatch a Bash command string to its rtk_cmd filter, if any.

Explicit registry: each entry is (regex, filter_fn). The filter receives both
the tool_result text AND the original command, so it can branch on flags
(e.g., `git log --oneline` needs different handling than `git log`).

Ordering matters: the first matching regex wins. Put more specific patterns
(`cargo test`, `cargo build`) before generic ones; put sub-command regexes
(`git status`, `git log`) before any hypothetical fallback `git` matcher.
"""
from __future__ import annotations

import re
from typing import Callable

from rtk_cmd.cargo import filter_cargo_build, filter_cargo_clippy, filter_cargo_test
from rtk_cmd.git import filter_git_diff, filter_git_log, filter_git_status
from rtk_cmd.pytest import filter_pytest_output
from rtk_cmd.js_tools import (
    filter_npm,
    filter_pnpm,
    filter_prettier,
    filter_tsc,
    filter_vitest,
)
from rtk_cmd.lint import filter_eslint, filter_pylint
from rtk_cmd.mcp_playwright import filter_playwright_tool
from rtk_cmd.mcp_tools import filter_mcp_tool
from rtk_cmd.python_tools import filter_mypy, filter_pip, filter_ruff


CmdFilter = Callable[[str, str], str]


def _wrap_ignore_cmd(fn: Callable[[str], str]) -> CmdFilter:
    """Adapt single-arg filters (pytest, cargo_*) to the (output, command) API."""
    def wrapped(output: str, _command: str) -> str:
        return fn(output)
    wrapped.__name__ = fn.__name__
    return wrapped


_PYTEST_RE = re.compile(r"(?:^|\s|/)pytest(?:\s|$)")
_CARGO_TEST_RE = re.compile(r"(?:^|\s|/)cargo\s+(?:--[^\s]+\s+)*(?:nextest\s+run|test)(?:\s|$)")
_CARGO_BUILD_RE = re.compile(r"(?:^|\s|/)cargo\s+(?:--[^\s]+\s+)*(?:build|check)(?:\s|$)")
_CARGO_CLIPPY_RE = re.compile(r"(?:^|\s|/)cargo\s+(?:--[^\s]+\s+)*clippy(?:\s|$)")
# Allow arbitrary global flags (including two-token forms like `-c color=never`)
# between `git` and the subcommand.
_GIT_STATUS_RE = re.compile(r"(?:^|\s|/)git\b(?:\s+\S+)*?\s+status(?:\s|$)")
_GIT_LOG_RE = re.compile(r"(?:^|\s|/)git\b(?:\s+\S+)*?\s+log(?:\s|$)")
# git show also produces diff-shaped output; route it through the same filter.
_GIT_DIFF_RE = re.compile(r"(?:^|\s|/)git\b(?:\s+\S+)*?\s+(?:diff|show)(?:\s|$)")
_RUFF_RE = re.compile(r"(?:^|\s|/)ruff(?:\s|$)")
_MYPY_RE = re.compile(r"(?:^|\s|/)mypy(?:\s|$)")
_PIP_RE = re.compile(r"(?:^|\s|/)pip3?(?:\s|$)")
# JS tools. Vitest + tsc can be invoked via npx/pnpm-exec, so match both plain
# and prefixed forms.
# lint tools. eslint often invoked via `npx eslint` or `pnpm exec eslint`.
_ESLINT_RE = re.compile(r"(?:^|\s|/)(?:npx\s+|pnpm\s+(?:exec\s+|run\s+)?|npm\s+(?:exec\s+)?)?eslint(?:\s|$)")
_PYLINT_RE = re.compile(r"(?:^|\s|/)pylint(?:\s|$)")
_PRETTIER_RE = re.compile(r"(?:^|\s|/)prettier(?:\s|$)")
_TSC_RE = re.compile(r"(?:^|\s|/)(?:npx\s+)?tsc(?:\s|$)")
_VITEST_RE = re.compile(r"(?:^|\s|/)(?:npx\s+|pnpm\s+(?:exec\s+|run\s+)?|npm\s+(?:exec\s+|test\s+)?)?vitest(?:\s|$)")
_PNPM_RE = re.compile(r"(?:^|\s|/)pnpm(?:\s|$)")
_NPM_RE = re.compile(r"(?:^|\s|/)npm(?:\s|$)")


_REGISTRY: list[tuple[re.Pattern, CmdFilter]] = [
    (_PYTEST_RE, _wrap_ignore_cmd(filter_pytest_output)),
    (_CARGO_TEST_RE, _wrap_ignore_cmd(filter_cargo_test)),
    (_CARGO_BUILD_RE, _wrap_ignore_cmd(filter_cargo_build)),
    (_CARGO_CLIPPY_RE, _wrap_ignore_cmd(filter_cargo_clippy)),
    (_GIT_STATUS_RE, filter_git_status),
    (_GIT_LOG_RE, filter_git_log),
    (_GIT_DIFF_RE, filter_git_diff),
    (_RUFF_RE, filter_ruff),
    (_MYPY_RE, filter_mypy),
    (_PIP_RE, filter_pip),
    # lint tools before vitest/tsc/pnpm/npm
    (_ESLINT_RE, filter_eslint),
    (_PYLINT_RE, filter_pylint),
    # prettier before vitest/tsc (all js tools) to avoid regex drift
    (_PRETTIER_RE, filter_prettier),
    (_VITEST_RE, filter_vitest),
    (_TSC_RE, filter_tsc),
    # pnpm/npm last: they may appear as prefixes in vitest/tsc commands
    (_PNPM_RE, filter_pnpm),
    (_NPM_RE, filter_npm),
]


def find_cmd_filter(command: str) -> CmdFilter | None:
    for pattern, fn in _REGISTRY:
        if pattern.search(command):
            return fn
    return None


# MCP tool registry: keyed by tool-name prefix. Separate from bash dispatch
# because MCP tools identify themselves by name (`mcp__playwright__...`),
# not by a shell command string.
_MCP_REGISTRY: list[tuple[str, Callable[[str, str], str]]] = [
    ("mcp__playwright__", filter_playwright_tool),
    ("mcp__plugin_playwright-mcp__", filter_playwright_tool),
    # zoekt search — both the legacy `mcp__zoekt__search` name and any
    # plugin-prefixed variant (`mcp__plugin_zoekt-mcp__search` etc.).
    ("mcp__zoekt__", filter_mcp_tool),
    ("mcp__plugin_zoekt-mcp__", filter_mcp_tool),
    # syno-build-mcp docker_execute — plugin variant only
    ("mcp__plugin_synology-dev-suite_syno-build-mcp__", filter_mcp_tool),
]


def find_mcp_filter(tool_name: str) -> Callable[[str, str], str] | None:
    for prefix, fn in _MCP_REGISTRY:
        if tool_name.startswith(prefix):
            return fn
    return None
