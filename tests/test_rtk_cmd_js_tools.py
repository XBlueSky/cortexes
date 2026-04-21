"""Ported subset of rtk's js/*.rs tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

from rtk_cmd.js_tools import (  # noqa: E402
    filter_npm_output,
    filter_pnpm_install,
    filter_prettier_output,
    filter_tsc_output,
    filter_vitest_output,
)


class Prettier(unittest.TestCase):
    def test_all_formatted(self):
        out = "\nChecking formatting...\nAll matched files use Prettier code style!\n"
        result = filter_prettier_output(out)
        self.assertIn("All files formatted correctly", result)

    def test_needs_formatting(self):
        out = """
Checking formatting...
src/components/ui/button.tsx
src/lib/auth/session.ts
src/pages/dashboard.tsx
Code style issues found in the above file(s). Forgot to run Prettier?
"""
        result = filter_prettier_output(out)
        self.assertIn("3 files need formatting", result)
        self.assertIn("button.tsx", result)
        self.assertIn("session.ts", result)

    def test_many_files(self):
        out = "Checking formatting...\n" + "".join(
            f"src/file{i}.ts\n" for i in range(15)
        ) + "Code style issues found\n"
        result = filter_prettier_output(out)
        self.assertIn("15 files need formatting", result)
        self.assertIn("... +5 more files", result)

    def test_empty(self):
        self.assertIn("Error", filter_prettier_output(""))


class Npm(unittest.TestCase):
    def test_strips_boilerplate(self):
        out = """
> project@1.0.0 build
> next build

npm WARN deprecated inflight@1.0.6: This module is not supported
npm notice

   Creating an optimized production build...
   ✓ Build completed
"""
        result = filter_npm_output(out)
        self.assertNotIn("npm WARN", result)
        self.assertNotIn("npm notice", result)
        self.assertNotIn("> project@", result)
        self.assertIn("Build completed", result)

    def test_empty(self):
        self.assertEqual(filter_npm_output("\n\n\n"), "ok")


class PnpmInstall(unittest.TestCase):
    def test_basic(self):
        out = """Progress: resolved 100, reused 80, downloaded 20, added 30
Packages: +30 -5
Progress: resolved 100, reused 100, done

Done in 2.3s
"""
        # Progress bars filtered out
        result = filter_pnpm_install(out)
        self.assertNotIn("Progress", result)

    def test_preserves_errors(self):
        out = """Progress: resolved 10
ERR_PNPM_NO_MATCHING_VERSION No matching version found for foo@^99.0.0
"""
        result = filter_pnpm_install(out)
        self.assertIn("ERR", result)


class Tsc(unittest.TestCase):
    def test_basic(self):
        out = """
src/server/api/auth.ts(12,5): error TS2322: Type 'string' is not assignable to type 'number'.
src/server/api/auth.ts(15,10): error TS2345: Argument of type 'number' is not assignable to parameter of type 'string'.
src/components/Button.tsx(8,3): error TS2339: Property 'onClick' does not exist on type 'ButtonProps'.
src/components/Button.tsx(10,5): error TS2322: Type 'string' is not assignable to type 'number'.

Found 4 errors in 2 files.
"""
        result = filter_tsc_output(out)
        self.assertIn("TypeScript: 4 errors in 2 files", result)
        self.assertIn("auth.ts (2 errors)", result)
        self.assertIn("Button.tsx (2 errors)", result)
        self.assertIn("TS2322", result)

    def test_every_error_message_shown(self):
        out = """
src/api.ts(10,5): error TS2322: Type 'string' is not assignable to type 'number'.
src/api.ts(20,5): error TS2322: Type 'boolean' is not assignable to type 'string'.
src/api.ts(30,5): error TS2322: Type 'null' is not assignable to type 'object'.
"""
        result = filter_tsc_output(out)
        self.assertIn("'string' is not assignable to type 'number'", result)
        self.assertIn("'boolean' is not assignable to type 'string'", result)
        self.assertIn("L10:", result)
        self.assertIn("L20:", result)
        self.assertIn("L30:", result)

    def test_continuation_lines(self):
        out = """
src/app.tsx(10,3): error TS2322: Type '{ children: Element; }' is not assignable to type 'Props'.
  Property 'children' does not exist on type 'Props'.
src/app.tsx(20,5): error TS2345: Argument of type 'number' is not assignable to parameter of type 'string'.
"""
        result = filter_tsc_output(out)
        self.assertIn("Property 'children' does not exist", result)

    def test_no_errors(self):
        self.assertIn("No errors found", filter_tsc_output("Found 0 errors.\n"))


class Vitest(unittest.TestCase):
    def test_json_all_pass(self):
        out = """{
  "numTotalTests": 50,
  "numPassedTests": 50,
  "numFailedTests": 0,
  "testResults": []
}"""
        result = filter_vitest_output(out)
        self.assertIn("50/50 passed", result)
        self.assertIn("0 failed", result)

    def test_json_with_failures(self):
        out = """{
  "numTotalTests": 10,
  "numPassedTests": 9,
  "numFailedTests": 1,
  "testResults": [
    {
      "name": "tests/foo.test.ts",
      "assertionResults": [
        {"fullName": "foo > bar should x", "status": "failed",
         "failureMessages": ["Error: expected 1 to be 2"]}
      ]
    }
  ]
}"""
        result = filter_vitest_output(out)
        self.assertIn("9/10 passed", result)
        self.assertIn("1 failed", result)
        self.assertIn("foo > bar", result)
        self.assertIn("expected 1 to be 2", result)

    def test_regex_fallback(self):
        out = """
 RUN  v1.0.0

 Test Files  1 failed | 9 passed (10)
      Tests  2 failed | 48 passed (50)
   Duration  1.23s
"""
        result = filter_vitest_output(out)
        self.assertIn("48/50 passed", result)
        self.assertIn("2 failed", result)

    def test_passthrough_truncation(self):
        # unparseable output falls through (but truncated to 8k)
        out = "x" * 9000
        result = filter_vitest_output(out)
        self.assertLessEqual(len(result), 8001 + 1)  # +1 for the truncation char


if __name__ == "__main__":
    unittest.main()
