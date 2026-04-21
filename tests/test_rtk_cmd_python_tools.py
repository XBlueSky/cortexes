"""Ported subset of rtk's ruff_cmd.rs / mypy_cmd.rs / pip_cmd.rs tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

from rtk_cmd.python_tools import (  # noqa: E402
    _compact_path,
    filter_mypy_output,
    filter_pip_list,
    filter_pip_outdated,
    filter_ruff_check_json,
    filter_ruff_format,
)


class RuffCheck(unittest.TestCase):
    def test_no_issues(self):
        result = filter_ruff_check_json("[]")
        self.assertIn("No issues found", result)

    def test_with_issues(self):
        output = """[
  {"code": "F401", "message": "`os` imported but unused",
   "location": {"row": 1, "column": 8}, "filename": "src/main.py",
   "fix": {"applicability": "safe"}},
  {"code": "F401", "message": "`sys` imported but unused",
   "location": {"row": 2, "column": 8}, "filename": "src/main.py",
   "fix": null},
  {"code": "E501", "message": "Line too long",
   "location": {"row": 10, "column": 89}, "filename": "src/utils.py",
   "fix": null}
]"""
        result = filter_ruff_check_json(output)
        self.assertIn("3 issues", result)
        self.assertIn("2 files", result)
        self.assertIn("1 fixable", result)
        self.assertIn("F401", result)
        self.assertIn("E501", result)
        self.assertIn("main.py", result)
        self.assertIn("utils.py", result)

    def test_not_json_passthrough(self):
        txt = "src/a.py:10:5: F401 `os` imported but unused\n"
        self.assertEqual(filter_ruff_check_json(txt), txt)


class RuffFormat(unittest.TestCase):
    def test_all_formatted(self):
        result = filter_ruff_format("5 files left unchanged")
        self.assertIn("All files formatted correctly", result)

    def test_needs_formatting(self):
        output = """Would reformat: src/main.py
Would reformat: tests/test_utils.py
2 files would be reformatted, 3 files left unchanged"""
        result = filter_ruff_format(output)
        self.assertIn("2 files need formatting", result)
        self.assertIn("main.py", result)
        self.assertIn("test_utils.py", result)
        self.assertIn("3 files already formatted", result)


class CompactPath(unittest.TestCase):
    def test_strips_prefixes(self):
        self.assertEqual(_compact_path("/Users/foo/project/src/main.py"), "src/main.py")
        self.assertEqual(_compact_path("/home/u/app/lib/utils.py"), "lib/utils.py")
        self.assertEqual(_compact_path("C:\\Users\\foo\\project\\tests\\test.py"), "tests/test.py")
        self.assertEqual(_compact_path("relative/file.py"), "file.py")


class Mypy(unittest.TestCase):
    def test_grouped_by_file(self):
        output = (
            "src/server/auth.py:12: error: Incompatible return value type  [return-value]\n"
            "src/server/auth.py:15: error: Argument 1 has incompatible type  [arg-type]\n"
            "src/models/user.py:8: error: Name \"foo\" is not defined  [name-defined]\n"
            "src/models/user.py:10: error: Incompatible types in assignment  [assignment]\n"
            "src/models/user.py:20: error: Missing return statement  [return]\n"
            "Found 5 errors in 2 files\n"
        )
        result = filter_mypy_output(output)
        self.assertIn("mypy: 5 errors in 2 files", result)
        user_pos = result.find("user.py")
        auth_pos = result.find("auth.py")
        self.assertLess(user_pos, auth_pos)
        self.assertIn("user.py (3 errors)", result)
        self.assertIn("auth.py (2 errors)", result)

    def test_with_column_numbers(self):
        result = filter_mypy_output(
            "src/api.py:10:5: error: Incompatible return value type  [return-value]\n"
        )
        self.assertIn("L10:", result)
        self.assertIn("[return-value]", result)

    def test_top_codes_summary(self):
        output = (
            "a.py:1: error: Error one  [return-value]\n"
            "a.py:2: error: Error two  [return-value]\n"
            "a.py:3: error: Error three  [return-value]\n"
            "b.py:1: error: Error four  [name-defined]\n"
            "c.py:1: error: Error five  [arg-type]\n"
        )
        result = filter_mypy_output(output)
        self.assertIn("Top codes:", result)
        self.assertIn("return-value (3x)", result)

    def test_single_code_no_summary(self):
        output = (
            "a.py:1: error: A  [return-value]\n"
            "b.py:1: error: B  [return-value]\n"
        )
        result = filter_mypy_output(output)
        self.assertNotIn("Top codes:", result)

    def test_note_continuation(self):
        output = (
            "src/app.py:10: error: Incompatible types in assignment  [assignment]\n"
            "src/app.py:10: note: Expected type \"int\"\n"
            "src/app.py:10: note: Got type \"str\"\n"
            "src/app.py:20: error: Missing return statement  [return]\n"
        )
        result = filter_mypy_output(output)
        self.assertIn("Incompatible types in assignment", result)
        self.assertIn("Expected type", result)
        self.assertIn("Got type", result)

    def test_fileless_errors_first(self):
        output = (
            "mypy: error: No module named 'nonexistent'\n"
            "src/api.py:10: error: Name \"foo\" is not defined  [name-defined]\n"
        )
        result = filter_mypy_output(output)
        self.assertIn("No module named", result)
        self.assertIn("api.py (1 errors", result)
        self.assertLess(result.find("No module named"), result.find("api.py"))

    def test_no_errors(self):
        self.assertEqual(
            filter_mypy_output("Success: no issues found in 5 source files\n"),
            "mypy: No issues found",
        )


class PipList(unittest.TestCase):
    def test_basic(self):
        output = """[
  {"name": "requests", "version": "2.31.0"},
  {"name": "pytest", "version": "7.4.0"},
  {"name": "rich", "version": "13.0.0"}
]"""
        result = filter_pip_list(output)
        self.assertIn("3 packages", result)
        self.assertIn("requests", result)
        self.assertIn("2.31.0", result)

    def test_empty(self):
        self.assertIn("No packages installed", filter_pip_list("[]"))

    def test_not_json_passthrough(self):
        txt = "Package    Version\n-------    -------\nrequests   2.31.0\n"
        self.assertEqual(filter_pip_list(txt), txt)


class PipOutdated(unittest.TestCase):
    def test_none(self):
        self.assertIn("up to date", filter_pip_outdated("[]"))

    def test_some(self):
        output = """[
  {"name": "requests", "version": "2.31.0", "latest_version": "2.32.0"},
  {"name": "pytest", "version": "7.4.0", "latest_version": "8.0.0"}
]"""
        result = filter_pip_outdated(output)
        self.assertIn("2 packages", result)
        self.assertIn("requests", result)
        self.assertIn("2.31.0 → 2.32.0", result)


if __name__ == "__main__":
    unittest.main()
