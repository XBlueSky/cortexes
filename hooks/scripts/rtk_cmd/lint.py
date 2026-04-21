"""Filter eslint / pylint / generic lint output.

Port of `filter_eslint_json`, `filter_pylint_json`, `filter_generic_lint`
and `compact_path` from rtk-ai/rtk's `src/cmds/js/lint_cmd.rs`
(MIT, © rtk-ai).

Dispatch maps to whichever filter fits the observed output shape:
- eslint: requires JSON (array of EslintResult); if not JSON, passthrough.
  (rtk spawns with `--format=json`.)
- pylint: requires JSON2 (array of PylintDiagnostic); same rule.
- generic: fallback for other linters — counts lines containing
  "error"/"warning" and shows a capped list. We only register generic for
  explicit commands (e.g. `biome check`) because it would mis-classify
  too many unrelated bash outputs.
"""
from __future__ import annotations

import json
from collections import defaultdict


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + "…"


def _compact_path(path: str) -> str:
    path = path.replace("\\", "/")
    for marker, prefix in (("/src/", "src/"), ("/lib/", "lib/"), ("/tests/", "tests/")):
        pos = path.rfind(marker)
        if pos != -1:
            return prefix + path[pos + len(marker):]
    pos = path.rfind("/")
    return path[pos + 1:] if pos != -1 else path


def _looks_like_json(output: str) -> bool:
    stripped = output.lstrip()
    return stripped.startswith("[") or stripped.startswith("{")


# ---------------------------------------------------------------------------
# eslint

def filter_eslint_json(output: str) -> str:
    if not _looks_like_json(output):
        return output
    try:
        results = json.loads(output)
    except json.JSONDecodeError:
        return output
    if not isinstance(results, list):
        return output

    total_errors = sum(r.get("errorCount", 0) for r in results)
    total_warnings = sum(r.get("warningCount", 0) for r in results)
    with_issues = [r for r in results if r.get("messages")]
    total_files = len(with_issues)

    if total_errors == 0 and total_warnings == 0:
        return "ESLint: No issues found"

    by_rule: dict[str, int] = defaultdict(int)
    for r in results:
        for m in r.get("messages", []):
            rule = m.get("ruleId")
            if rule:
                by_rule[rule] += 1

    by_file = sorted(
        ((r, len(r.get("messages", []))) for r in with_issues),
        key=lambda kv: kv[1],
        reverse=True,
    )

    parts = [
        f"ESLint: {total_errors} errors, {total_warnings} warnings in {total_files} files",
        "═══════════════════════════════════════",
    ]

    rule_counts = sorted(by_rule.items(), key=lambda kv: kv[1], reverse=True)
    if rule_counts:
        parts.append("Top rules:")
        for rule, count in rule_counts[:10]:
            parts.append(f"  {rule} ({count}x)")
        parts.append("")

    parts.append("Top files:")
    for file_result, count in by_file[:10]:
        short = _compact_path(file_result.get("filePath", "?"))
        parts.append(f"  {short} ({count} issues)")

        file_rules: dict[str, int] = defaultdict(int)
        for m in file_result.get("messages", []):
            rule = m.get("ruleId")
            if rule:
                file_rules[rule] += 1
        for rule, c in sorted(file_rules.items(), key=lambda kv: kv[1], reverse=True)[:3]:
            parts.append(f"    {rule} ({c})")

    if len(by_file) > 10:
        parts.append("")
        parts.append(f"... +{len(by_file) - 10} more files")

    return "\n".join(parts).strip()


def filter_eslint(output: str, command: str) -> str:
    return filter_eslint_json(output)


# ---------------------------------------------------------------------------
# pylint

def filter_pylint_json(output: str) -> str:
    if not _looks_like_json(output):
        return output
    try:
        diagnostics = json.loads(output)
    except json.JSONDecodeError:
        return output
    if not isinstance(diagnostics, list):
        return output

    if not diagnostics:
        return "Pylint: No issues found"

    errors = warnings = conventions = refactors = 0
    for d in diagnostics:
        t = d.get("type", "")
        if t == "error":
            errors += 1
        elif t == "warning":
            warnings += 1
        elif t == "convention":
            conventions += 1
        elif t == "refactor":
            refactors += 1

    unique_files = {d.get("path", "?") for d in diagnostics}

    by_symbol: dict[str, int] = defaultdict(int)
    for d in diagnostics:
        key = f"{d.get('symbol', '?')} ({d.get('message-id', '?')})"
        by_symbol[key] += 1

    by_file: dict[str, int] = defaultdict(int)
    for d in diagnostics:
        by_file[d.get("path", "?")] += 1

    parts = [f"Pylint: {len(diagnostics)} issues in {len(unique_files)} files"]
    if errors > 0 or warnings > 0:
        sev = f"  {errors} errors, {warnings} warnings"
        if conventions > 0 or refactors > 0:
            sev += f", {conventions} conventions, {refactors} refactors"
        parts.append(sev)
    parts.append("═══════════════════════════════════════")

    symbol_counts = sorted(by_symbol.items(), key=lambda kv: kv[1], reverse=True)
    if symbol_counts:
        parts.append("Top rules:")
        for sym, count in symbol_counts[:10]:
            parts.append(f"  {sym} ({count}x)")
        parts.append("")

    file_counts = sorted(by_file.items(), key=lambda kv: kv[1], reverse=True)
    parts.append("Top files:")
    for file, count in file_counts[:10]:
        parts.append(f"  {_compact_path(file)} ({count} issues)")
        file_symbols: dict[str, int] = defaultdict(int)
        for d in diagnostics:
            if d.get("path") == file:
                k = f"{d.get('symbol', '?')} ({d.get('message-id', '?')})"
                file_symbols[k] += 1
        for sym, c in sorted(file_symbols.items(), key=lambda kv: kv[1], reverse=True)[:3]:
            parts.append(f"    {sym} ({c})")

    if len(file_counts) > 10:
        parts.append("")
        parts.append(f"... +{len(file_counts) - 10} more files")

    return "\n".join(parts).strip()


def filter_pylint(output: str, command: str) -> str:
    return filter_pylint_json(output)


# ---------------------------------------------------------------------------
# generic (biome, other custom linters)

def filter_generic_lint(output: str) -> str:
    warnings = 0
    errors = 0
    issues: list[str] = []
    for line in output.splitlines():
        lower = line.lower()
        if "warning" in lower:
            warnings += 1
            issues.append(line)
        if "error" in lower and "0 error" not in lower:
            errors += 1
            issues.append(line)

    if errors == 0 and warnings == 0:
        return "Lint: No issues found"

    parts = [
        f"Lint: {errors} errors, {warnings} warnings",
        "═══════════════════════════════════════",
    ]
    for issue in issues[:20]:
        parts.append(_truncate(issue, 100))
    if len(issues) > 20:
        parts.append("")
        parts.append(f"... +{len(issues) - 20} more issues")
    return "\n".join(parts).strip()
