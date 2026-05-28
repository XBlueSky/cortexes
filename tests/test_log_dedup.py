"""Port of rtk's inline #[test] cases for src/cmds/system/log_cmd.rs,
plus extra coverage for the dedup_or_passthrough wrapper.

Run with: python3 -m unittest tests.test_log_dedup
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

from log_dedup import (  # noqa: E402
    analyze_logs,
    dedup_or_passthrough,
    normalize_log_line,
)


class NormalizeLogLine(unittest.TestCase):
    def test_strips_iso_timestamp(self):
        self.assertEqual(
            normalize_log_line("2024-01-01 10:00:00 ERROR: boom"),
            "ERROR: boom",
        )

    def test_replaces_uuid(self):
        n = normalize_log_line("req=550e8400-e29b-41d4-a716-446655440000 done")
        self.assertIn("<UUID>", n)
        self.assertNotIn("550e8400", n)

    def test_replaces_hex_and_big_num(self):
        n = normalize_log_line("addr=0xdeadbeef tid=123456")
        self.assertIn("<HEX>", n)
        self.assertIn("<NUM>", n)

    def test_replaces_path(self):
        n = normalize_log_line("read /var/log/foo.log failed")
        self.assertIn("<PATH>", n)

    def test_two_lines_with_different_timestamp_normalize_equal(self):
        a = normalize_log_line("2024-01-01 10:00:01 ERROR: conn fail")
        b = normalize_log_line("2024-01-01 10:00:02 ERROR: conn fail")
        self.assertEqual(a, b)


class AnalyzeLogs(unittest.TestCase):
    def test_dedup_counts_repeats(self):
        logs = (
            "2024-01-01 10:00:00 ERROR: Connection failed to /api/server\n"
            "2024-01-01 10:00:01 ERROR: Connection failed to /api/server\n"
            "2024-01-01 10:00:02 ERROR: Connection failed to /api/server\n"
            "2024-01-01 10:00:03 WARN: Retrying connection\n"
            "2024-01-01 10:00:04 INFO: Connected\n"
        )
        result = analyze_logs(logs)
        self.assertIn("[x3]", result)
        self.assertIn("[ERRORS]", result)
        self.assertIn("3 errors (1 unique)", result)
        self.assertIn("1 warnings (1 unique)", result)
        self.assertIn("1 info messages", result)

    def test_extended_severity_keywords(self):
        logs = (
            "2024-01-01 10:00:00 CRITICAL: disk full\n"
            "2024-01-01 10:00:01 ALERT: memory pressure\n"
            "2024-01-01 10:00:02 emerg: system shutdown imminent\n"
            "2024-01-01 10:00:03 SEVERE: data corruption detected\n"
            "2024-01-01 10:00:04 notice: config reloaded\n"
        )
        result = analyze_logs(logs)
        self.assertIn("[ERRORS]", result)
        self.assertIn("[WARNINGS]", result)
        self.assertIn("4 errors (4 unique)", result)
        self.assertIn("1 warnings (1 unique)", result)

    def test_multibyte_no_panic(self):
        prefix = "ข้อผิดพลาด" * 15
        logs = f"2024-01-01 10:00:00 ERROR: {prefix} connection failed\n"
        result = analyze_logs(logs)
        self.assertIn("[ERRORS]", result)

    def test_lines_without_severity_are_skipped(self):
        logs = "just some boring noise\nnothing here\n"
        result = analyze_logs(logs)
        self.assertIn("0 errors", result)
        self.assertIn("0 warnings", result)
        self.assertNotIn("[ERRORS]", result)

    def test_overflow_more_unique_errors(self):
        lines = [f"2024-01-01 10:00:{i:02d} ERROR: kind {i} failure" for i in range(15)]
        result = analyze_logs("\n".join(lines))
        self.assertIn("+5 more unique errors", result)


class DedupOrPassthrough(unittest.TestCase):
    def test_short_input_falls_through(self):
        text = "trivial single error line\n"
        out, used = dedup_or_passthrough(text)
        self.assertFalse(used)
        self.assertEqual(out, text)

    def test_repeated_errors_compress(self):
        text = "\n".join(
            f"2024-01-01 10:00:{i:02d} ERROR: same boring failure" for i in range(50)
        )
        out, used = dedup_or_passthrough(text)
        self.assertTrue(used)
        self.assertLess(len(out), len(text))
        self.assertIn("[x50]", out)


if __name__ == "__main__":
    unittest.main()
