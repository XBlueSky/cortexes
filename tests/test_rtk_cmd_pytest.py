"""Port of rtk's inline #[test] cases for src/cmds/python/pytest_cmd.rs.

Run with: python3 -m unittest tests.test_rtk_cmd_pytest
(from repo root, with hooks/scripts on sys.path).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

from rtk_cmd.pytest import filter_pytest_output, parse_summary_line  # noqa: E402


class FilterPytestOutput(unittest.TestCase):
    def test_all_pass(self):
        output = """=== test session starts ===
platform darwin -- Python 3.11.0
collected 5 items

tests/test_foo.py .....                                            [100%]

=== 5 passed in 0.50s ==="""
        result = filter_pytest_output(output)
        self.assertIn("Pytest", result)
        self.assertIn("5 passed", result)

    def test_with_failures(self):
        output = """=== test session starts ===
collected 5 items

tests/test_foo.py ..F..                                            [100%]

=== FAILURES ===
___ test_something ___

    def test_something():
>       assert False
E       assert False

tests/test_foo.py:10: AssertionError

=== short test summary info ===
FAILED tests/test_foo.py::test_something - assert False
=== 4 passed, 1 failed in 0.50s ==="""
        result = filter_pytest_output(output)
        self.assertIn("4 passed, 1 failed", result)
        self.assertIn("test_something", result)
        self.assertIn("assert False", result)

    def test_multiple_failures(self):
        output = """=== test session starts ===
collected 3 items

tests/test_foo.py FFF                                              [100%]

=== FAILURES ===
___ test_one ___
E   AssertionError: expected 5

___ test_two ___
E   ValueError: invalid value

=== short test summary info ===
FAILED tests/test_foo.py::test_one - AssertionError: expected 5
FAILED tests/test_foo.py::test_two - ValueError: invalid value
FAILED tests/test_foo.py::test_three - KeyError
=== 3 failed in 0.20s ==="""
        result = filter_pytest_output(output)
        self.assertIn("3 failed", result)
        self.assertIn("test_one", result)
        self.assertIn("test_two", result)
        self.assertIn("expected 5", result)

    def test_no_tests(self):
        output = """=== test session starts ===
collected 0 items

=== no tests ran in 0.00s ==="""
        result = filter_pytest_output(output)
        self.assertIn("No tests collected", result)

    def test_quiet_mode_failures(self):
        output = """=== test session starts ===
platform linux -- Python 3.12.11, pytest-8.1.0
collected 1705 items

.......F.......

=== FAILURES ===
___ test_something ___

E   AssertionError: expected True

=== short test summary info ===
FAILED tests/test_foo.py::test_something - AssertionError
5 failed, 1698 passed, 2 skipped in 108.89s"""
        result = filter_pytest_output(output)
        self.assertNotIn("No tests collected", result)
        self.assertTrue(
            "1698" in result or "5 failed" in result,
            f"Should show actual test counts. Got: {result}",
        )

    def test_only_skipped(self):
        output = """=== test session starts ===
collected 3 items

=== 3 skipped in 0.10s ==="""
        result = filter_pytest_output(output)
        self.assertNotIn("No tests collected", result)


class ParseSummaryLine(unittest.TestCase):
    def test_passed_only(self):
        self.assertEqual(parse_summary_line("=== 5 passed in 0.50s ==="), (5, 0, 0))

    def test_passed_failed(self):
        self.assertEqual(
            parse_summary_line("=== 4 passed, 1 failed in 0.50s ==="),
            (4, 1, 0),
        )

    def test_all_three(self):
        self.assertEqual(
            parse_summary_line("=== 3 passed, 1 failed, 2 skipped in 1.0s ==="),
            (3, 1, 2),
        )


if __name__ == "__main__":
    unittest.main()
