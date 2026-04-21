"""Filter ruff, mypy, pip output.

Port of selected pure filter functions from rtk-ai/rtk (MIT, © rtk-ai):
- `src/cmds/python/ruff_cmd.rs`: `filter_ruff_check_json`, `filter_ruff_format`
- `src/cmds/python/mypy_cmd.rs`: `filter_mypy_output`
- `src/cmds/python/pip_cmd.rs`: `filter_pip_list`, `filter_pip_outdated`

ADAPTATION: rtk spawns these tools with JSON flags (`--output-format=json`,
`--format=json`) so its filters assume JSON input. In our environment we
consume captured output from whatever the user actually ran, which is
usually text. Each JSON-expecting filter now sniffs the input: if it's
not JSON we return the original verbatim (no destructive fallback to
`JSON parse failed: ...` which would replace the user's context).
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field


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
# ruff check (JSON)

def filter_ruff_check_json(output: str) -> str:
    if not _looks_like_json(output):
        return output
    try:
        diagnostics = json.loads(output)
    except json.JSONDecodeError:
        return output
    if not isinstance(diagnostics, list):
        return output

    if not diagnostics:
        return "Ruff: No issues found"

    total = len(diagnostics)
    fixable = sum(1 for d in diagnostics if d.get("fix") is not None)
    files = {d.get("filename", "?") for d in diagnostics}

    by_rule: dict[str, int] = defaultdict(int)
    by_file: dict[str, int] = defaultdict(int)
    for d in diagnostics:
        by_rule[d.get("code", "?")] += 1
        by_file[d.get("filename", "?")] += 1

    parts: list[str] = []
    header = f"Ruff: {total} issues in {len(files)} files"
    if fixable > 0:
        header += f" ({fixable} fixable)"
    parts.append(header)
    parts.append("═══════════════════════════════════════")

    rule_counts = sorted(by_rule.items(), key=lambda kv: kv[1], reverse=True)
    if rule_counts:
        parts.append("Top rules:")
        for rule, count in rule_counts[:10]:
            parts.append(f"  {rule} ({count}x)")
        parts.append("")

    file_counts = sorted(by_file.items(), key=lambda kv: kv[1], reverse=True)
    parts.append("Top files:")
    for file, count in file_counts[:10]:
        parts.append(f"  {_compact_path(file)} ({count} issues)")
        file_rules: dict[str, int] = defaultdict(int)
        for d in diagnostics:
            if d.get("filename") == file:
                file_rules[d.get("code", "?")] += 1
        for rule, c in sorted(file_rules.items(), key=lambda kv: kv[1], reverse=True)[:3]:
            parts.append(f"    {rule} ({c})")

    if len(file_counts) > 10:
        parts.append("")
        parts.append(f"... +{len(file_counts) - 10} more files")

    if fixable > 0:
        parts.append("")
        parts.append(f"[hint] Run `ruff check --fix` to auto-fix {fixable} issues")

    return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# ruff format (text)

def filter_ruff_format(output: str) -> str:
    files_to_format: list[str] = []
    files_checked = 0

    for line in output.splitlines():
        trimmed = line.strip()
        lower = trimmed.lower()

        if "would reformat:" in lower:
            tail = trimmed.split(":", 1)
            if len(tail) > 1:
                files_to_format.append(tail[1].strip())

        if "left unchanged" in lower:
            for part in trimmed.split(","):
                if "left unchanged" not in part.lower():
                    continue
                words = part.split()
                for i, w in enumerate(words):
                    if w in ("file", "files") and i > 0:
                        try:
                            files_checked = int(words[i - 1])
                        except ValueError:
                            pass
                        break
                break

    output_lower = output.lower()

    if not files_to_format and "left unchanged" in output_lower:
        return "Ruff format: All files formatted correctly"

    if "would reformat" in output_lower:
        if not files_to_format:
            return "Ruff format: All files formatted correctly"
        parts = [
            f"Ruff format: {len(files_to_format)} files need formatting",
            "═══════════════════════════════════════",
        ]
        for i, file in enumerate(files_to_format[:10]):
            parts.append(f"{i + 1}. {_compact_path(file)}")
        if len(files_to_format) > 10:
            parts.append("")
            parts.append(f"... +{len(files_to_format) - 10} more files")
        if files_checked > 0:
            parts.append("")
            parts.append(f"{files_checked} files already formatted")
        parts.append("")
        parts.append("[hint] Run `ruff format` to format these files")
        return "\n".join(parts).strip()

    return output.strip()


def filter_ruff(output: str, command: str) -> str:
    # `ruff format` has distinct text output; `ruff check` is JSON-or-text.
    if " format" in command or command.endswith(" format"):
        return filter_ruff_format(output)
    if _looks_like_json(output):
        return filter_ruff_check_json(output)
    return output


# ---------------------------------------------------------------------------
# mypy

_MYPY_DIAG_RE = re.compile(
    r"^(.+?):(\d+)(?::\d+)?: (error|warning|note): (.+?)(?:\s+\[(.+)\])?$"
)


@dataclass
class _MypyError:
    file: str
    line: int
    code: str
    message: str
    context_lines: list[str] = field(default_factory=list)


def filter_mypy_output(output: str) -> str:
    lines = output.splitlines()
    errors: list[_MypyError] = []
    fileless: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        if line.startswith("Found ") and " error" in line:
            i += 1
            continue
        if line.startswith("Success:"):
            i += 1
            continue

        m = _MYPY_DIAG_RE.match(line)
        if m:
            file = m.group(1)
            line_num = int(m.group(2)) if m.group(2).isdigit() else 0
            severity = m.group(3)
            message = m.group(4)
            code = m.group(5) or ""

            if severity == "note":
                if errors and errors[-1].file == file:
                    errors[-1].context_lines.append(message)
                    i += 1
                    continue
                fileless.append(line)
                i += 1
                continue

            err = _MypyError(file=file, line=line_num, code=code, message=message)
            i += 1
            while i < len(lines):
                m2 = _MYPY_DIAG_RE.match(lines[i])
                if m2 and m2.group(3) == "note" and m2.group(1) == err.file:
                    err.context_lines.append(m2.group(4))
                    i += 1
                    continue
                break
            errors.append(err)
        elif "error:" in line and line.strip():
            fileless.append(line)
            i += 1
        else:
            i += 1

    if not errors and not fileless:
        return "mypy: No issues found"

    by_file: dict[str, list[_MypyError]] = defaultdict(list)
    for e in errors:
        by_file[e.file].append(e)

    by_code: dict[str, int] = defaultdict(int)
    for e in errors:
        if e.code:
            by_code[e.code] += 1

    parts: list[str] = []
    for line in fileless:
        parts.append(line)
    if fileless and errors:
        parts.append("")

    if errors:
        parts.append(f"mypy: {len(errors)} errors in {len(by_file)} files")
        parts.append("═══════════════════════════════════════")

        code_counts = sorted(by_code.items(), key=lambda kv: kv[1], reverse=True)
        if len(code_counts) > 1:
            codes_str = ", ".join(f"{c} ({n}x)" for c, n in code_counts[:5])
            parts.append(f"Top codes: {codes_str}")
            parts.append("")

        files_sorted = sorted(by_file.items(), key=lambda kv: len(kv[1]), reverse=True)
        for file, ferrs in files_sorted:
            parts.append(f"{file} ({len(ferrs)} errors)")
            for err in ferrs:
                tag = f"[{err.code}] " if err.code else ""
                parts.append(f"  L{err.line}: {tag}{_truncate(err.message, 120)}")
                for ctx in err.context_lines:
                    parts.append(f"    {_truncate(ctx, 120)}")
            parts.append("")

    return "\n".join(parts).strip()


def filter_mypy(output: str, command: str) -> str:
    return filter_mypy_output(output)


# ---------------------------------------------------------------------------
# pip list / pip outdated

def filter_pip_list(output: str) -> str:
    if not _looks_like_json(output):
        return output
    try:
        packages = json.loads(output)
    except json.JSONDecodeError:
        return output
    if not isinstance(packages, list):
        return output

    if not packages:
        return "pip list: No packages installed"

    parts = [f"pip list: {len(packages)} packages", "═══════════════════════════════════════"]

    by_letter: dict[str, list[dict]] = defaultdict(list)
    for p in packages:
        name = p.get("name", "?")
        letter = name[0].lower() if name else "?"
        by_letter[letter].append(p)

    for letter in sorted(by_letter):
        pkgs = by_letter[letter]
        parts.append("")
        parts.append(f"[{letter.upper()}]")
        for p in pkgs[:10]:
            parts.append(f"  {p.get('name', '?')} ({p.get('version', '?')})")
        if len(pkgs) > 10:
            parts.append(f"  ... +{len(pkgs) - 10} more")

    return "\n".join(parts).strip()


def filter_pip_outdated(output: str) -> str:
    if not _looks_like_json(output):
        return output
    try:
        packages = json.loads(output)
    except json.JSONDecodeError:
        return output
    if not isinstance(packages, list):
        return output

    if not packages:
        return "pip outdated: All packages up to date"

    parts = [f"pip outdated: {len(packages)} packages", "═══════════════════════════════════════"]
    for i, p in enumerate(packages[:20]):
        latest = p.get("latest_version") or "unknown"
        parts.append(f"{i + 1}. {p.get('name', '?')} ({p.get('version', '?')} → {latest})")

    if len(packages) > 20:
        parts.append("")
        parts.append(f"... +{len(packages) - 20} more packages")

    parts.append("")
    parts.append("[hint] Run `pip install --upgrade <package>` to update")
    return "\n".join(parts).strip()


def filter_pip(output: str, command: str) -> str:
    # pip has many subcommands; only list/outdated are compressible here.
    # Others (install, show, search, freeze) go through unchanged.
    if " list" in command:
        return filter_pip_list(output)
    if " outdated" in command:
        return filter_pip_outdated(output)
    return output
