"""Ported subset of rtk's lint_cmd.rs tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

from rtk_cmd.lint import (  # noqa: E402
    _compact_path,
    filter_eslint_json,
    filter_generic_lint,
    filter_pylint_json,
)


class Eslint(unittest.TestCase):
    def test_basic(self):
        json = """[
          {
            "filePath": "/Users/test/project/src/utils.ts",
            "messages": [
              {"ruleId": "prefer-const", "severity": 1, "message": "Use const", "line": 10, "column": 5},
              {"ruleId": "prefer-const", "severity": 1, "message": "Use const", "line": 15, "column": 5}
            ],
            "errorCount": 0, "warningCount": 2
          },
          {
            "filePath": "/Users/test/project/src/api.ts",
            "messages": [
              {"ruleId": "@typescript-eslint/no-unused-vars", "severity": 2,
               "message": "Variable x is unused", "line": 20, "column": 10}
            ],
            "errorCount": 1, "warningCount": 0
          }
        ]"""
        result = filter_eslint_json(json)
        self.assertIn("ESLint:", result)
        self.assertIn("prefer-const", result)
        self.assertIn("no-unused-vars", result)
        self.assertIn("src/utils.ts", result)
        self.assertIn("1 errors, 2 warnings", result)

    def test_no_issues(self):
        json = """[{"filePath": "a.ts", "messages": [], "errorCount": 0, "warningCount": 0}]"""
        self.assertIn("No issues found", filter_eslint_json(json))

    def test_not_json_passthrough(self):
        txt = "some eslint text output\n"
        self.assertEqual(filter_eslint_json(txt), txt)


class CompactPath(unittest.TestCase):
    def test_strips_prefixes(self):
        self.assertEqual(_compact_path("/Users/foo/project/src/utils.ts"), "src/utils.ts")
        self.assertEqual(_compact_path("C:\\Users\\project\\src\\api.ts"), "src/api.ts")
        self.assertEqual(_compact_path("simple.ts"), "simple.ts")


class Pylint(unittest.TestCase):
    def test_no_issues(self):
        self.assertIn("No issues found", filter_pylint_json("[]"))

    def test_with_issues(self):
        json = """[
          {"type": "warning", "module": "main", "obj": "", "line": 10, "column": 0,
           "path": "src/main.py", "symbol": "unused-variable",
           "message": "Unused variable x", "message-id": "W0612"},
          {"type": "warning", "module": "main", "obj": "foo", "line": 15, "column": 4,
           "path": "src/main.py", "symbol": "unused-variable",
           "message": "Unused variable y", "message-id": "W0612"},
          {"type": "error", "module": "utils", "obj": "bar", "line": 20, "column": 0,
           "path": "src/utils.py", "symbol": "undefined-variable",
           "message": "Undefined variable z", "message-id": "E0602"}
        ]"""
        result = filter_pylint_json(json)
        self.assertIn("3 issues", result)
        self.assertIn("2 files", result)
        self.assertIn("1 errors, 2 warnings", result)
        self.assertIn("unused-variable (W0612)", result)
        self.assertIn("undefined-variable (E0602)", result)
        self.assertIn("main.py", result)
        self.assertIn("utils.py", result)


class GenericLint(unittest.TestCase):
    def test_no_issues(self):
        self.assertIn("No issues found", filter_generic_lint(""))

    def test_counts_errors_and_warnings(self):
        # rtk's generic filter counts every line containing "warning"/"error",
        # including summary lines — matching that behaviour.
        out = """src/a.ts:10: warning: foo
src/b.ts:20: error: bar"""
        result = filter_generic_lint(out)
        self.assertIn("1 errors", result)
        self.assertIn("1 warnings", result)


if __name__ == "__main__":
    unittest.main()
