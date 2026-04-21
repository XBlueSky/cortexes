"""Filter cargo output.

Port of three pure filter functions from rtk-ai/rtk's
`src/cmds/rust/cargo_cmd.rs` (MIT, © rtk-ai):

- filter_cargo_build
- filter_cargo_test
- filter_cargo_clippy

Rust's `BlockHandler` trait and the `BlockStreamFilter` streaming runner are
NOT ported — we only consume already-captured output, so the handler's
`should_skip` / `is_block_start` / `is_block_continuation` methods are inlined
as module-private helpers inside `filter_cargo_build`.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# helpers

def _truncate(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "…"


# ---------------------------------------------------------------------------
# cargo build

def filter_cargo_build(output: str) -> str:
    compiled = 0
    warnings = 0
    error_count = 0
    finished_line: str | None = None

    blocks: list[list[str]] = []
    current_block: list[str] = []
    in_block = False

    def should_skip(line: str) -> bool:
        nonlocal compiled, finished_line
        trimmed = line.lstrip()
        if trimmed.startswith("Compiling") or trimmed.startswith("Checking"):
            compiled += 1
            return True
        if trimmed.startswith("Downloading") or trimmed.startswith("Downloaded"):
            return True
        if trimmed.startswith("Finished"):
            finished_line = trimmed
            return True
        if (
            line.startswith("warning:")
            and "generated" in line
            and "warning" in line
        ):
            return True
        if (line.startswith("error:") or line.startswith("error[")) and (
            "aborting due to" in line or "could not compile" in line
        ):
            return True
        return False

    def is_block_start(line: str) -> bool:
        nonlocal error_count, warnings
        if line.startswith("error[") or line.startswith("error:"):
            error_count += 1
            return True
        if line.startswith("warning:") or line.startswith("warning["):
            warnings += 1
            return True
        return False

    def is_block_continuation(line: str, block: list[str]) -> bool:
        return not (not line.strip() and len(block) > 3)

    for line in output.splitlines():
        if should_skip(line):
            continue
        if is_block_start(line):
            if in_block and current_block:
                blocks.append(current_block)
                current_block = []
            in_block = True
            current_block.append(line)
        elif in_block:
            if is_block_continuation(line, current_block):
                current_block.append(line)
            else:
                blocks.append(current_block)
                current_block = []
                in_block = False

    if current_block:
        blocks.append(current_block)

    if error_count == 0 and warnings == 0:
        s = f"cargo build ({compiled} crates compiled)"
        if finished_line:
            s = f"{s}\n{finished_line}"
        return s

    parts = [
        f"cargo build: {error_count} errors, {warnings} warnings ({compiled} crates)",
        "═══════════════════════════════════════",
    ]
    shown = blocks[:15]
    for i, blk in enumerate(shown):
        parts.append("\n".join(blk))
        if i < len(shown) - 1:
            parts.append("")
    if len(blocks) > 15:
        parts.append("")
        parts.append(f"... +{len(blocks) - 15} more issues")
    return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# cargo test

_TEST_RESULT_RE = re.compile(
    r"test result: (\w+)\.\s+(\d+) passed;\s+(\d+) failed;\s+(\d+) ignored;"
    r"\s+(\d+) measured;\s+(\d+) filtered out"
    r"(?:;\s+finished in ([\d.]+)s)?"
)


@dataclass
class _AggregatedTestResult:
    passed: int = 0
    failed: int = 0
    ignored: int = 0
    measured: int = 0
    filtered_out: int = 0
    suites: int = 0
    duration_secs: float = 0.0
    has_duration: bool = False

    @classmethod
    def parse_line(cls, line: str) -> "_AggregatedTestResult | None":
        m = _TEST_RESULT_RE.search(line)
        if not m:
            return None
        status = m.group(1)
        if status != "ok":
            return None
        try:
            passed = int(m.group(2))
            failed = int(m.group(3))
            ignored = int(m.group(4))
            measured = int(m.group(5))
            filtered_out = int(m.group(6))
        except ValueError:
            return None
        duration_match = m.group(7)
        if duration_match:
            try:
                duration_secs = float(duration_match)
            except ValueError:
                duration_secs = 0.0
            has_duration = True
        else:
            duration_secs = 0.0
            has_duration = False
        return cls(
            passed=passed,
            failed=failed,
            ignored=ignored,
            measured=measured,
            filtered_out=filtered_out,
            suites=1,
            duration_secs=duration_secs,
            has_duration=has_duration,
        )

    def merge(self, other: "_AggregatedTestResult") -> None:
        self.passed += other.passed
        self.failed += other.failed
        self.ignored += other.ignored
        self.measured += other.measured
        self.filtered_out += other.filtered_out
        self.suites += other.suites
        self.duration_secs += other.duration_secs
        self.has_duration = self.has_duration and other.has_duration

    def format_compact(self) -> str:
        parts = [f"{self.passed} passed"]
        if self.ignored > 0:
            parts.append(f"{self.ignored} ignored")
        if self.filtered_out > 0:
            parts.append(f"{self.filtered_out} filtered out")
        counts = ", ".join(parts)
        suite_text = "1 suite" if self.suites == 1 else f"{self.suites} suites"
        if self.has_duration:
            return f"cargo test: {counts} ({suite_text}, {self.duration_secs:.2f}s)"
        return f"cargo test: {counts} ({suite_text})"


def filter_cargo_test(output: str) -> str:
    failures: list[str] = []
    summary_lines: list[str] = []
    in_failure_section = False
    current_failure: list[str] = []

    for line in output.splitlines():
        ls = line.lstrip()
        if (
            ls.startswith("Compiling")
            or ls.startswith("Downloading")
            or ls.startswith("Downloaded")
            or ls.startswith("Finished")
        ):
            continue

        if line.startswith("running ") or (
            line.startswith("test ") and line.endswith("... ok")
        ):
            continue

        if line == "failures:":
            in_failure_section = True
            continue

        if in_failure_section:
            if line.startswith("test result:"):
                in_failure_section = False
                summary_lines.append(line)
            elif line.startswith("    ") or line.startswith("---- "):
                current_failure.append(line)
            elif not line.strip() and current_failure:
                failures.append("\n".join(current_failure))
                current_failure = []
            elif line.strip():
                current_failure.append(line)

        if not in_failure_section and line.startswith("test result:"):
            summary_lines.append(line)

    if current_failure:
        failures.append("\n".join(current_failure))

    if not failures and summary_lines:
        aggregated: _AggregatedTestResult | None = None
        all_parsed = True
        for line in summary_lines:
            parsed = _AggregatedTestResult.parse_line(line)
            if parsed is None:
                all_parsed = False
                break
            if aggregated is None:
                aggregated = parsed
            else:
                aggregated.merge(parsed)
        if all_parsed and aggregated is not None and aggregated.suites > 0:
            return aggregated.format_compact()
        return "\n".join(summary_lines).strip()

    result_parts: list[str] = []
    if failures:
        result_parts.append(f"FAILURES ({len(failures)}):")
        result_parts.append("═══════════════════════════════════════")
        for i, failure in enumerate(failures[:10]):
            result_parts.append(f"{i + 1}. {_truncate(failure, 200)}")
        if len(failures) > 10:
            result_parts.append("")
            result_parts.append(f"... +{len(failures) - 10} more failures")
        result_parts.append("")

    for line in summary_lines:
        result_parts.append(line)

    result = "\n".join(result_parts).strip()
    if result:
        return result

    # fallback
    has_compile_errors = any(
        l.lstrip().startswith("error[") or l.lstrip().startswith("error:")
        for l in output.splitlines()
    )
    if has_compile_errors:
        build_filtered = filter_cargo_build(output)
        if build_filtered.startswith("cargo build:"):
            return build_filtered.replace("cargo build:", "cargo test:", 1)

    meaningful = [
        l for l in output.splitlines()
        if l.strip() and not l.lstrip().startswith("Compiling")
    ]
    return "\n".join(meaningful[-5:])


# ---------------------------------------------------------------------------
# cargo clippy

def filter_cargo_clippy(output: str) -> str:
    by_rule: dict[str, list[str]] = defaultdict(list)
    error_count = 0
    warning_count = 0
    error_blocks: list[list[str]] = []

    current_rule = ""
    in_error = False
    current_block: list[str] = []

    for line in output.splitlines():
        ls = line.lstrip()
        if (
            ls.startswith("Compiling")
            or ls.startswith("Checking")
            or ls.startswith("Downloading")
            or ls.startswith("Downloaded")
            or ls.startswith("Finished")
        ):
            if in_error and current_block:
                error_blocks.append(current_block)
                current_block = []
                in_error = False
            continue

        if (
            ("generated" in line and "warning" in line)
            or "aborting due to" in line
            or "could not compile" in line
        ):
            continue

        is_error_line = line.startswith("error:") or line.startswith("error[")
        is_warning_line = line.startswith("warning:") or line.startswith("warning[")

        if is_error_line or is_warning_line:
            if in_error and current_block:
                error_blocks.append(current_block)
                current_block = []
            in_error = False

            if is_error_line:
                error_count += 1
                in_error = True
                current_block.append(line)
            else:
                warning_count += 1

            bracket_start = line.rfind("[")
            bracket_end = line.rfind("]")
            if bracket_start != -1 and bracket_end != -1 and bracket_end > bracket_start:
                current_rule = line[bracket_start + 1:bracket_end]
            else:
                prefix = "error: " if is_error_line else "warning: "
                current_rule = line.removeprefix(prefix) if line.startswith(prefix) else line

        elif line.lstrip().startswith("--> "):
            location = line.lstrip().removeprefix("--> ")
            if current_rule:
                by_rule[current_rule].append(location)
            if in_error:
                current_block.append(line)

        elif in_error:
            if not line.strip():
                if current_block:
                    error_blocks.append(current_block)
                    current_block = []
                in_error = False
            elif len(current_block) < 15:
                current_block.append(line)

    if in_error and current_block:
        error_blocks.append(current_block)

    if error_count == 0 and warning_count == 0:
        return "cargo clippy: No issues found"

    parts: list[str] = [
        f"cargo clippy: {error_count} errors, {warning_count} warnings",
        "═══════════════════════════════════════",
    ]

    if error_blocks:
        parts.append("")
        parts.append("Errors:")
        for block in error_blocks[:10]:
            for bl in block:
                parts.append(f"  {_truncate(bl, 160)}")
            parts.append("")
        if len(error_blocks) > 10:
            parts.append(f"  ... +{len(error_blocks) - 10} more errors")

    # Sort warning rules by frequency desc
    rule_counts = sorted(by_rule.items(), key=lambda kv: len(kv[1]), reverse=True)

    for rule, locations in rule_counts[:15]:
        parts.append(f"  {rule} ({len(locations)}x)")
        for loc in locations[:3]:
            parts.append(f"    {loc}")
        if len(locations) > 3:
            parts.append(f"    ... +{len(locations) - 3} more")

    if len(by_rule) > 15:
        parts.append("")
        parts.append(f"... +{len(by_rule) - 15} more rules")

    return "\n".join(parts).strip()
