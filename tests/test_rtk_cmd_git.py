"""Ported subset of rtk's git.rs tests (status + log + parse_user_limit)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

from rtk_cmd.git import (  # noqa: E402
    condense_unified_diff,
    filter_git_diff,
    filter_git_log,
    filter_git_status,
    filter_log_output,
    format_status_output,
    parse_user_limit,
)


class FormatStatusOutput(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(format_status_output(""), "Clean working tree")

    def test_modified_files(self):
        porc = "## main...origin/main\n M src/main.rs\n M src/lib.rs\n"
        result = format_status_output(porc)
        self.assertIn("* main...origin/main", result)
        self.assertIn("~ Modified: 2 files", result)
        self.assertIn("src/main.rs", result)
        self.assertNotIn("Staged", result)
        self.assertNotIn("Untracked", result)

    def test_untracked(self):
        porc = "## feature/new\n?? temp.txt\n?? debug.log\n?? test.sh\n"
        result = format_status_output(porc)
        self.assertIn("? Untracked: 3 files", result)
        self.assertIn("temp.txt", result)

    def test_mixed_changes(self):
        porc = """## main
M  staged.rs
 M modified.rs
A  added.rs
?? untracked.txt
"""
        result = format_status_output(porc)
        self.assertIn("+ Staged: 2 files", result)
        self.assertIn("~ Modified: 1 files", result)
        self.assertIn("? Untracked: 1 files", result)

    def test_staged_truncation(self):
        porc = "## main\n" + "".join(f"M  file{i}.rs\n" for i in range(1, 21))
        result = format_status_output(porc)
        self.assertIn("+ Staged: 20 files", result)
        self.assertIn("file1.rs", result)
        self.assertIn("file15.rs", result)
        self.assertIn("... +5 more", result)
        self.assertNotIn("file16.rs", result)


class ParseUserLimit(unittest.TestCase):
    def test_combined(self):
        self.assertEqual(parse_user_limit(["-20"]), 20)

    def test_n_space(self):
        self.assertEqual(parse_user_limit(["-n", "15"]), 15)

    def test_max_count_eq(self):
        self.assertEqual(parse_user_limit(["--max-count=30"]), 30)

    def test_max_count_space(self):
        self.assertEqual(parse_user_limit(["--max-count", "25"]), 25)

    def test_none(self):
        self.assertIsNone(parse_user_limit(["--oneline"]))


class FilterLogOutput(unittest.TestCase):
    def test_basic(self):
        output = (
            "abc1234 This is a commit message (2 days ago) <author>\n\n---END---\n"
            "def5678 Another commit (1 week ago) <other>\n\n---END---\n"
        )
        result = filter_log_output(output, 10, False, False)
        self.assertIn("abc1234", result)
        self.assertIn("def5678", result)
        self.assertEqual(len(result.splitlines()), 2)

    def test_with_body(self):
        output = (
            "abc1234 feat: add feature (2 days ago) <author>\n"
            "BREAKING CHANGE: removed old API\n"
            "Signed-off-by: Author <a@b.com>\n"
            "---END---\n"
            "def5678 fix: typo (1 day ago) <other>\n\n---END---\n"
        )
        result = filter_log_output(output, 10, False, False)
        self.assertIn("abc1234", result)
        self.assertIn("BREAKING CHANGE: removed old API", result)
        self.assertNotIn("Signed-off-by:", result)
        self.assertIn("def5678", result)

    def test_skips_trailers(self):
        output = (
            "abc1234 chore: bump (1 day ago) <bot>\n"
            "Signed-off-by: Bot <bot@ci>\n"
            "Co-authored-by: Human <h@b>\n"
            "---END---\n"
        )
        result = filter_log_output(output, 10, False, False)
        self.assertIn("abc1234", result)
        self.assertNotIn("Signed-off-by:", result)
        self.assertEqual(len(result.splitlines()), 1)

    def test_truncate_long(self):
        long_line = "abc1234 " + "x" * 100 + " (2 days ago) <author>"
        result = filter_log_output(long_line, 10, False, False)
        # Marker-absent → falls into user_format path → line truncation
        self.assertLess(len(result), len(long_line))
        self.assertIn("...", result)
        self.assertLessEqual(len(result), 80)

    def test_cap_lines(self):
        output = "\n".join(
            f"hash{i} message {i} (1 day ago) <author>\n\n---END---" for i in range(20)
        )
        result = filter_log_output(output, 5, False, False)
        self.assertEqual(len(result.splitlines()), 5)

    def test_user_limit_no_cap(self):
        output = "\n".join(
            f"hash{i} message {i} (1 day ago) <author>\n\n---END---" for i in range(20)
        )
        result = filter_log_output(output, 20, True, False)
        self.assertEqual(len(result.splitlines()), 20)


class FilterGitLogEntryPoint(unittest.TestCase):
    def test_plain_git_log_marker_less_input(self):
        # Real-world capture: no ---END---, so entry point should do line truncation
        output = "abc1234 fix bug\ndef5678 add feature\n"
        result = filter_git_log(output, "git log")
        self.assertIn("abc1234", result)
        self.assertIn("def5678", result)

    def test_oneline_with_user_limit(self):
        lines = [f"hash{i} msg{i}" for i in range(20)]
        output = "\n".join(lines)
        result = filter_git_log(output, "git log --oneline -5")
        self.assertEqual(len(result.splitlines()), 20)  # user_set_limit → no cap


class FilterGitStatusEntryPoint(unittest.TestCase):
    def test_porcelain_dispatch(self):
        porc = "## main\n M src/lib.rs\n"
        result = filter_git_status(porc, "git status --porcelain=v1 --branch")
        self.assertIn("* main", result)
        self.assertIn("Modified", result)

    def test_human_readable_dispatch(self):
        human = """On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
"""
        result = filter_git_status(human, "git status")
        self.assertIn("nothing to commit", result)


class CondenseUnifiedDiff(unittest.TestCase):
    def test_single_file(self):
        diff = """diff --git a/src/main.rs b/src/main.rs
--- a/src/main.rs
+++ b/src/main.rs
@@ -1,3 +1,4 @@
 fn main() {
+    println!("hello");
     println!("world");
 }
"""
        result = condense_unified_diff(diff)
        self.assertIn("src/main.rs", result)
        self.assertIn("+1", result)
        self.assertIn("println", result)

    def test_multiple_files(self):
        diff = """diff --git a/a.rs b/a.rs
--- a/a.rs
+++ b/a.rs
+added line
diff --git a/b.rs b/b.rs
--- a/b.rs
+++ b/b.rs
-removed line
"""
        result = condense_unified_diff(diff)
        self.assertIn("a.rs", result)
        self.assertIn("b.rs", result)

    def test_empty(self):
        self.assertEqual(condense_unified_diff(""), "")

    def test_no_overflow_for_small_change(self):
        diff = """diff --git a/x.rs b/x.rs
--- a/x.rs
+++ b/x.rs
+a
+b
-c
-d
"""
        result = condense_unified_diff(diff)
        self.assertNotIn("more", result)

    def test_strips_b_prefix(self):
        diff = """diff --git a/path/file.py b/path/file.py
--- a/path/file.py
+++ b/path/file.py
+new line
"""
        result = condense_unified_diff(diff)
        self.assertIn("path/file.py", result)
        self.assertNotIn("b/path/file.py", result)


class FilterGitDiffEntryPoint(unittest.TestCase):
    def test_dispatch(self):
        diff = """diff --git a/f.py b/f.py
--- a/f.py
+++ b/f.py
+new
"""
        result = filter_git_diff(diff, "git diff")
        self.assertIn("f.py", result)
        self.assertIn("+1", result)


if __name__ == "__main__":
    unittest.main()
