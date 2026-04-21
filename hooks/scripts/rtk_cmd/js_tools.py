"""Filter js/ts tool output — npm, pnpm (install), tsc, vitest, prettier.

Port of selected pure filter functions from rtk-ai/rtk's `src/cmds/js/` (MIT,
© rtk-ai). Entry points take (output, command) and are dispatched by regex
on the bash command string.

Not ported this pass:
- ESLint (`lint_cmd.rs`, 691 LOC) — complex, deferred
- Next.js (`next_cmd.rs`) — framework-specific, low frequency
- Prisma (`prisma_cmd.rs`) — ORM-specific
- Playwright (`playwright_cmd.rs`) — UI tests, has own format
- pnpm list/outdated — text-state-machine parsing, deferred
  (pnpm install is ported; the more common case)

ADAPTATIONS:
- `filter_vitest`: rtk has a trait-based `OutputParser` scaffold we don't
  need. Collapsed to a single function: JSON → regex → passthrough.
- rtk spawns tsc as `tsc --pretty false --noEmit`; our captured input
  might include pretty colours. We strip ANSI before matching.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + "…"


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\[\d[0-9;]*[A-Za-z]")


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


# ---------------------------------------------------------------------------
# prettier

def filter_prettier_output(output: str) -> str:
    if not output.strip():
        return "Error: prettier produced no output"

    files_to_format: list[str] = []
    files_checked = 0
    _PRETTIER_EXTS = (".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".css", ".scss")

    for line in output.splitlines():
        trimmed = line.strip()
        if (
            trimmed
            and not trimmed.startswith("Checking")
            and not trimmed.startswith("All matched")
            and not trimmed.startswith("Code style")
            and "[warn]" not in trimmed
            and "[error]" not in trimmed
            and any(trimmed.endswith(ext) for ext in _PRETTIER_EXTS)
        ):
            files_to_format.append(trimmed)

        if "All matched files use Prettier" in trimmed:
            first = trimmed.split()[0] if trimmed.split() else ""
            if first.isdigit():
                files_checked = int(first)

    if not files_to_format and "All matched files use Prettier" in output:
        return "Prettier: All files formatted correctly"

    is_check_mode = True
    if "modified" in output or "formatted" in output:
        is_check_mode = False

    if not is_check_mode:
        return f"Prettier: {len(files_to_format)} files formatted"

    if not files_to_format:
        return "Prettier: All files formatted correctly"

    parts = [
        f"Prettier: {len(files_to_format)} files need formatting",
        "═══════════════════════════════════════",
    ]
    for i, f in enumerate(files_to_format[:10]):
        parts.append(f"{i + 1}. {f}")
    if len(files_to_format) > 10:
        parts.append("")
        parts.append(f"... +{len(files_to_format) - 10} more files")
    if files_checked > 0:
        parts.append("")
        parts.append(f"{files_checked - len(files_to_format)} files already formatted")
    return "\n".join(parts).strip()


def filter_prettier(output: str, command: str) -> str:
    return filter_prettier_output(output)


# ---------------------------------------------------------------------------
# npm (generic output stripping)

def filter_npm_output(output: str) -> str:
    result = []
    for line in output.splitlines():
        if line.startswith(">") and "@" in line:
            continue
        ls = line.lstrip()
        if ls.startswith("npm WARN") or ls.startswith("npm notice"):
            continue
        if "⸩" in line or "⸨" in line or ("..." in line and len(line) < 10):
            continue
        if not line.strip():
            continue
        result.append(line)
    return "\n".join(result) if result else "ok"


def filter_npm(output: str, command: str) -> str:
    return filter_npm_output(output)


# ---------------------------------------------------------------------------
# pnpm install

def filter_pnpm_install(output: str) -> str:
    result = []
    saw_progress = False
    for line in output.splitlines():
        if "Progress" in line or "│" in line or "%" in line:
            saw_progress = True
            continue
        if saw_progress and not line.strip():
            continue
        if "ERR" in line or "error" in line or "ERROR" in line:
            result.append(line)
            continue
        if (
            "packages in" in line
            or "dependencies" in line
            or line.startswith("+")
            or line.startswith("-")
        ):
            result.append(line.strip())
    return "\n".join(result) if result else "ok"


def filter_pnpm(output: str, command: str) -> str:
    # Only the install subcommand has a meaningful filter here.
    if " install" in command or " i " in command or command.endswith(" i") or " add " in command:
        return filter_pnpm_install(output)
    return output


# ---------------------------------------------------------------------------
# tsc

_TSC_ERROR_RE = re.compile(
    r"^(.+?)\((\d+),(\d+)\):\s+(error|warning)\s+(TS\d+):\s+(.+)$"
)


@dataclass
class _TsError:
    file: str
    line: int
    code: str
    message: str
    context_lines: list[str]


def filter_tsc_output(output: str) -> str:
    output = _strip_ansi(output)
    lines = output.splitlines()
    errors: list[_TsError] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _TSC_ERROR_RE.match(line)
        if m:
            err = _TsError(
                file=m.group(1),
                line=int(m.group(2)) if m.group(2).isdigit() else 0,
                code=m.group(5),
                message=m.group(6),
                context_lines=[],
            )
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if (
                    nxt
                    and (nxt.startswith("  ") or nxt.startswith("\t"))
                    and not _TSC_ERROR_RE.match(nxt)
                ):
                    err.context_lines.append(nxt.strip())
                    i += 1
                else:
                    break
            errors.append(err)
        else:
            i += 1

    if not errors:
        if "Found 0 errors" in output:
            return "TypeScript: No errors found"
        return "TypeScript compilation completed"

    by_file: dict[str, list[_TsError]] = defaultdict(list)
    for e in errors:
        by_file[e.file].append(e)
    by_code: dict[str, int] = defaultdict(int)
    for e in errors:
        by_code[e.code] += 1

    parts = [
        f"TypeScript: {len(errors)} errors in {len(by_file)} files",
        "═══════════════════════════════════════",
    ]
    code_counts = sorted(by_code.items(), key=lambda kv: kv[1], reverse=True)
    if len(code_counts) > 1:
        codes_str = ", ".join(f"{c} ({n}x)" for c, n in code_counts[:5])
        parts.append(f"Top codes: {codes_str}")
        parts.append("")

    files_sorted = sorted(by_file.items(), key=lambda kv: len(kv[1]), reverse=True)
    for file, ferrs in files_sorted:
        parts.append(f"{file} ({len(ferrs)} errors)")
        for err in ferrs:
            parts.append(f"  L{err.line}: {err.code} {_truncate(err.message, 120)}")
            for ctx in err.context_lines:
                parts.append(f"    {_truncate(ctx, 120)}")
        parts.append("")
    return "\n".join(parts).strip()


def filter_tsc(output: str, command: str) -> str:
    return filter_tsc_output(output)


# ---------------------------------------------------------------------------
# vitest

_VITEST_STATS_RE = re.compile(
    r"Tests\s+(?:(\d+)\s+failed\s+\|\s+)?(\d+)\s+passed"
)
_VITEST_DURATION_RE = re.compile(r"Duration\s+([\d.]+)(ms|s)")


def _extract_json_object(text: str) -> str | None:
    """Strip prefix lines like `> vitest` and extract the top-level JSON."""
    brace = text.find("{")
    if brace == -1:
        return None
    # naive: find the matching closing brace
    depth = 0
    for i in range(brace, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[brace:i + 1]
    return None


def filter_vitest_output(output: str) -> str:
    stripped = output.strip()

    # Tier 1: try JSON
    json_data = None
    if stripped.startswith("{"):
        try:
            json_data = json.loads(stripped)
        except json.JSONDecodeError:
            pass
    if json_data is None:
        obj = _extract_json_object(output)
        if obj is not None:
            try:
                json_data = json.loads(obj)
            except json.JSONDecodeError:
                pass

    if isinstance(json_data, dict) and "numTotalTests" in json_data:
        total = json_data.get("numTotalTests", 0)
        passed = json_data.get("numPassedTests", 0)
        failed = json_data.get("numFailedTests", 0)
        pending = json_data.get("numPendingTests", 0)
        failures = []
        for file in json_data.get("testResults", []):
            fname = file.get("name", "")
            for t in file.get("assertionResults", []):
                if t.get("status") == "failed":
                    failures.append((
                        t.get("fullName", "?"),
                        fname,
                        "\n".join(t.get("failureMessages", [])),
                    ))

        parts = [f"Vitest: {passed}/{total} passed, {failed} failed"]
        if pending:
            parts[0] += f", {pending} pending"
        if failures:
            parts.append("═══════════════════════════════════════")
            for i, (name, fpath, msg) in enumerate(failures[:10]):
                parts.append(f"{i + 1}. [FAIL] {name}")
                if fpath:
                    parts.append(f"     file: {fpath}")
                for ml in msg.splitlines()[:3]:
                    parts.append(f"     {_truncate(ml, 120)}")
            if len(failures) > 10:
                parts.append("")
                parts.append(f"... +{len(failures) - 10} more failures")
        return "\n".join(parts).strip()

    # Tier 2: regex
    clean = _strip_ansi(output)
    m = _VITEST_STATS_RE.search(clean)
    if m:
        failed = int(m.group(1)) if m.group(1) else 0
        passed = int(m.group(2)) if m.group(2) else 0
        total = passed + failed
        dm = _VITEST_DURATION_RE.search(clean)
        if dm:
            value = float(dm.group(1))
            if dm.group(2) == "s":
                value *= 1000
            duration = f", {value:.0f}ms"
        else:
            duration = ""
        header = f"Vitest: {passed}/{total} passed, {failed} failed{duration}"
        return header

    # Tier 3: passthrough (truncated)
    return _truncate(output, 8000)


def filter_vitest(output: str, command: str) -> str:
    return filter_vitest_output(output)
