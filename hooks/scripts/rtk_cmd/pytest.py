"""Filter pytest output down to failures and the summary line.

Port of rtk-ai/rtk's `src/cmds/python/pytest_cmd.rs` (MIT, © rtk-ai).
Only the three pure filter functions are ported — rtk's `run()` wrapper
(spawning pytest as a CLI tool) is out of scope; we only consume captured
output from Claude Code's Bash tool_result.
"""
from __future__ import annotations

from enum import Enum, auto


class _State(Enum):
    HEADER = auto()
    TEST_PROGRESS = auto()
    FAILURES = auto()
    SUMMARY = auto()


def _truncate(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "…"


def parse_summary_line(summary: str) -> tuple[int, int, int]:
    """Parse a pytest summary line into (passed, failed, skipped)."""
    passed = failed = skipped = 0
    for part in summary.split(","):
        words = part.split()
        for i, word in enumerate(words):
            if i == 0:
                continue
            prev = words[i - 1]
            try:
                n = int(prev)
            except ValueError:
                continue
            if "passed" in word:
                passed = n
            elif "failed" in word:
                failed = n
            elif "skipped" in word:
                skipped = n
    return passed, failed, skipped


def filter_pytest_output(output: str) -> str:
    """Reduce full pytest output to summary + selected failures."""
    state = _State.HEADER
    test_files: list[str] = []
    failures: list[str] = []
    current_failure: list[str] = []
    summary_line = ""

    for line in output.splitlines():
        trimmed = line.strip()

        if trimmed.startswith("===") and "test session starts" in trimmed:
            state = _State.HEADER
            continue
        if trimmed.startswith("===") and "FAILURES" in trimmed:
            state = _State.FAILURES
            continue
        if trimmed.startswith("===") and "short test summary" in trimmed:
            state = _State.SUMMARY
            if current_failure:
                failures.append("\n".join(current_failure))
                current_failure = []
            continue
        if trimmed.startswith("===") and (
            "passed" in trimmed or "failed" in trimmed or "skipped" in trimmed
        ):
            summary_line = trimmed
            continue
        # quiet mode (-q): bare summary without === wrapper
        if (
            not summary_line
            and not trimmed.startswith("===")
            and not trimmed.startswith("FAILED")
            and not trimmed.startswith("ERROR")
            and (" passed" in trimmed or " failed" in trimmed or " skipped" in trimmed)
            and " in " in trimmed
        ):
            summary_line = trimmed
            continue

        if state is _State.HEADER:
            if trimmed.startswith("collected"):
                state = _State.TEST_PROGRESS
        elif state is _State.TEST_PROGRESS:
            if (
                trimmed
                and not trimmed.startswith("===")
                and (".py" in trimmed or "%]" in trimmed)
            ):
                test_files.append(trimmed)
        elif state is _State.FAILURES:
            if trimmed.startswith("___"):
                if current_failure:
                    failures.append("\n".join(current_failure))
                    current_failure = []
                current_failure.append(trimmed)
            elif trimmed and not trimmed.startswith("==="):
                current_failure.append(trimmed)
        elif state is _State.SUMMARY:
            if trimmed.startswith("FAILED") or trimmed.startswith("ERROR"):
                failures.append(trimmed)

    if current_failure:
        failures.append("\n".join(current_failure))

    return _build_pytest_summary(summary_line, test_files, failures)


def _build_pytest_summary(
    summary: str, _test_files: list[str], failures: list[str]
) -> str:
    passed, failed, skipped = parse_summary_line(summary)

    if failed == 0 and passed > 0:
        return f"Pytest: {passed} passed"

    if passed == 0 and failed == 0 and skipped == 0:
        return "Pytest: No tests collected"

    parts: list[str] = [f"Pytest: {passed} passed, {failed} failed"]
    if skipped > 0:
        parts[0] += f", {skipped} skipped"
    parts.append("═══════════════════════════════════════")

    if not failures:
        return "\n".join(parts).strip()

    parts.append("")
    parts.append("Failures:")

    shown = failures[:5]
    for i, failure in enumerate(shown):
        lines = failure.splitlines()
        first = lines[0] if lines else ""

        if first.startswith("___"):
            test_name = first.strip("_").strip()
            parts.append(f"{i + 1}. [FAIL] {test_name}")
        elif first.startswith("FAILED"):
            split = first.split(" - ", 1)
            test_path = split[0].removeprefix("FAILED ")
            parts.append(f"{i + 1}. [FAIL] {test_path}")
            if len(split) > 1:
                parts.append(f"     {_truncate(split[1], 100)}")
            continue
        else:
            # no leading marker; still emit an entry for traceability
            parts.append(f"{i + 1}. [FAIL] {first}")

        relevant = 0
        for line in lines[1:]:
            stripped = line.strip()
            low = line.lower()
            is_relevant = (
                stripped.startswith(">")
                or stripped.startswith("E")
                or "assert" in low
                or "error" in low
                or ".py:" in line
            )
            if is_relevant and relevant < 3:
                parts.append(f"     {_truncate(line, 100)}")
                relevant += 1

        if i < len(shown) - 1:
            parts.append("")

    if len(failures) > 5:
        parts.append("")
        parts.append(f"... +{len(failures) - 5} more failures")

    return "\n".join(parts).strip()
