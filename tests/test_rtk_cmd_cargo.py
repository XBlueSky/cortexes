"""Ported subset of rtk's cargo_cmd.rs tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

from rtk_cmd.cargo import (  # noqa: E402
    filter_cargo_build,
    filter_cargo_clippy,
    filter_cargo_test,
)


class FilterCargoBuild(unittest.TestCase):
    def test_success(self):
        output = """   Compiling libc v0.2.153
   Compiling cfg-if v1.0.0
   Compiling rtk v0.5.0
    Finished dev [unoptimized + debuginfo] target(s) in 15.23s
"""
        result = filter_cargo_build(output)
        self.assertIn("cargo build", result)
        self.assertIn("3 crates compiled", result)

    def test_errors(self):
        output = """   Compiling rtk v0.5.0
error[E0308]: mismatched types
 --> src/main.rs:10:5
  |
10|     "hello"
  |     ^^^^^^^ expected `i32`, found `&str`

error: aborting due to 1 previous error
"""
        result = filter_cargo_build(output)
        self.assertIn("1 errors", result)
        self.assertIn("E0308", result)
        self.assertIn("mismatched types", result)


class FilterCargoTest(unittest.TestCase):
    def test_all_pass(self):
        output = """   Compiling rtk v0.5.0
    Finished test [unoptimized + debuginfo] target(s) in 2.53s
     Running target/debug/deps/rtk-abc123

running 15 tests
test utils::tests::test_truncate_short_string ... ok
test utils::tests::test_truncate_long_string ... ok
test utils::tests::test_strip_ansi_simple ... ok

test result: ok. 15 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s
"""
        result = filter_cargo_test(output)
        self.assertIn("cargo test: 15 passed (1 suite, 0.01s)", result)
        self.assertNotIn("Compiling", result)

    def test_failures(self):
        output = """running 5 tests
test foo::test_a ... ok
test foo::test_b ... FAILED
test foo::test_c ... ok

failures:

---- foo::test_b stdout ----
thread 'foo::test_b' panicked at 'assert_eq!(1, 2)'

failures:
    foo::test_b

test result: FAILED. 4 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out
"""
        result = filter_cargo_test(output)
        self.assertIn("FAILURES", result)
        self.assertIn("test_b", result)
        self.assertIn("test result:", result)

    def test_multi_suite_all_pass(self):
        output = """     Running unittests src/lib.rs

running 50 tests
test result: ok. 50 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.45s

     Running unittests src/main.rs

running 30 tests
test result: ok. 30 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.30s

     Running tests/integration.rs

running 25 tests
test result: ok. 25 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.25s

   Doc-tests rtk

running 32 tests
test result: ok. 32 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.45s
"""
        result = filter_cargo_test(output)
        self.assertIn("cargo test: 137 passed (4 suites, 1.45s)", result)

    def test_with_ignored_and_filtered(self):
        output = """     Running unittests src/lib.rs

running 50 tests
test result: ok. 45 passed; 0 failed; 3 ignored; 0 measured; 2 filtered out; finished in 0.50s

     Running tests/integration.rs

running 20 tests
test result: ok. 18 passed; 0 failed; 2 ignored; 0 measured; 0 filtered out; finished in 0.20s
"""
        result = filter_cargo_test(output)
        self.assertIn(
            "cargo test: 63 passed, 5 ignored, 2 filtered out (2 suites, 0.70s)",
            result,
        )

    def test_single_suite_compact_singular(self):
        output = """running 15 tests
test result: ok. 15 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s
"""
        result = filter_cargo_test(output)
        self.assertIn("(1 suite,", result)

    def test_regex_fallback(self):
        output = """running 15 tests
test result: MALFORMED LINE WITHOUT PROPER FORMAT
"""
        result = filter_cargo_test(output)
        self.assertIn("MALFORMED", result)


class FilterCargoClippy(unittest.TestCase):
    def test_clean(self):
        output = """    Checking rtk v0.5.0
    Finished dev [unoptimized + debuginfo] target(s) in 1.53s
"""
        self.assertIn("No issues found", filter_cargo_clippy(output))

    def test_warnings_grouped(self):
        output = """    Checking rtk v0.5.0
warning: unused variable: `x` [unused_variables]
 --> src/main.rs:10:9
  |
10|     let x = 5;

warning: this function has too many arguments [clippy::too_many_arguments]
 --> src/git.rs:16:1
  |

warning: `rtk` (bin) generated 2 warnings
    Finished dev [unoptimized + debuginfo] target(s) in 1.53s
"""
        result = filter_cargo_clippy(output)
        self.assertIn("0 errors, 2 warnings", result)
        self.assertIn("unused_variables", result)
        self.assertIn("clippy::too_many_arguments", result)

    def test_error_details(self):
        output = """    Checking rtk v0.5.0
error: struct literals are not allowed here
warning: unused variable: `x` [unused_variables]
    Finished dev [unoptimized + debuginfo] target(s) in 1.53s
"""
        result = filter_cargo_clippy(output)
        self.assertIn("1 errors, 1 warnings", result)
        self.assertIn("Errors:", result)
        self.assertIn("struct literals are not allowed here", result)


if __name__ == "__main__":
    unittest.main()
