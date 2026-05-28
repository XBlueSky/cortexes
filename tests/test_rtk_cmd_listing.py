"""Listing filter tests (find / grep / ls / tree / wc / cat-like)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

from rtk_cmd.dispatch import find_cmd_filter  # noqa: E402
from rtk_cmd.listing import (  # noqa: E402
    filter_cat_like,
    filter_find,
    filter_grep,
    filter_ls,
    filter_tree,
    filter_wc,
)


class FindFilter(unittest.TestCase):
    def test_short_passthrough(self):
        text = "./a.py\n./b.py\n./c.py\n"
        self.assertEqual(filter_find(text), text)

    def test_long_head_tail(self):
        lines = [f"./pkg/dir{i}/file{i}.py" for i in range(200)]
        text = "\n".join(lines)
        result = filter_find(text)
        self.assertIn("./pkg/dir0/", result)
        self.assertIn("./pkg/dir199/", result)
        self.assertIn("paths omitted", result)
        self.assertLess(len(result), len(text))


class GrepFilter(unittest.TestCase):
    def _mk(self, files):
        lines = []
        for f, matches in files.items():
            for ln, content in matches:
                lines.append(f"{f}:{ln}:{content}")
        return "\n".join(lines) + "\n"

    def test_groups_and_caps(self):
        files = {
            f"src/dir{i}/file{i}.py": [(j * 10, f"hit {i}-{j}") for j in range(8)]
            for i in range(3)
        }
        text = self._mk(files)
        result = filter_grep(text)
        self.assertIn("24 matches in 3 files", result)
        # 5-per-file cap → 15 lines + header. Each file should have first 5 hits.
        for i in range(3):
            self.assertIn(f"src/dir{i}/file{i}.py:0: hit {i}-0", result)
            self.assertIn(f"src/dir{i}/file{i}.py:40: hit {i}-4", result)
            # 6th hit dropped
            self.assertNotIn(f"hit {i}-5", result)

    def test_global_cap(self):
        files = {
            f"f{i}.py": [(j, f"line {j}") for j in range(3)]  # 3 each
            for i in range(30)  # 30 files × 3 = 90 hits
        }
        text = self._mk(files)
        result = filter_grep(text)
        self.assertIn("90 matches in 30 files", result)
        self.assertIn("more matches omitted", result)

    def test_no_grep_shape_passthrough(self):
        text = "just some unrelated text\nno colons here\n"
        self.assertEqual(filter_grep(text), text)

    def test_truncates_long_lines(self):
        text = "f.py:1:" + "x" * 500 + "\n"
        result = filter_grep(text)
        self.assertIn("...", result)
        self.assertNotIn("x" * 300, result)

    def test_grows_skips_filter(self):
        # Single small match — output would be longer than input, return raw.
        text = "f.py:1:short\n"
        result = filter_grep(text)
        self.assertEqual(result, text)


class LsFilter(unittest.TestCase):
    def test_strips_total_header(self):
        text = "total 24\ndrwxr-xr-x  1 u u   42 May 28 10:00 src\n-rw-r--r--  1 u u  100 May 28 10:00 a.txt\n"
        result = filter_ls(text)
        self.assertNotIn("total", result)
        self.assertIn("src", result)
        self.assertIn("a.txt", result)

    def test_caps_huge_listing(self):
        lines = [f"-rw-r--r-- 1 u u {i} May 28 10:00 file{i}.txt" for i in range(200)]
        text = "\n".join(lines)
        result = filter_ls(text)
        self.assertIn("entries omitted", result)
        self.assertIn("file0.txt", result)
        self.assertIn("file199.txt", result)


class TreeFilter(unittest.TestCase):
    def test_strips_summary(self):
        text = (
            ".\n"
            "├── src\n"
            "│   └── main.rs\n"
            "└── Cargo.toml\n"
            "\n"
            "2 directories, 3 files\n"
        )
        result = filter_tree(text)
        self.assertNotIn("directories", result)
        self.assertNotIn("files", result)
        self.assertIn("main.rs", result)
        self.assertIn("Cargo.toml", result)

    def test_preserves_structure(self):
        text = ".\n├── src\n│   ├── main.rs\n│   └── lib.rs\n└── tests\n"
        result = filter_tree(text)
        self.assertIn("├──", result)
        self.assertIn("│", result)
        self.assertIn("└──", result)

    def test_caps_huge_tree(self):
        lines = ["."] + [f"├── file{i}.txt" for i in range(300)]
        text = "\n".join(lines) + "\n\n300 directories, 300 files\n"
        result = filter_tree(text)
        self.assertIn("tree lines omitted", result)
        self.assertNotIn("directories", result)


class WcFilter(unittest.TestCase):
    def test_short_passthrough(self):
        text = "   42 file.py\n"
        self.assertEqual(filter_wc(text), text)

    def test_many_files_keeps_total(self):
        lines = [f"  {i*3} file{i}.py" for i in range(100)] + ["  300 total"]
        text = "\n".join(lines)
        result = filter_wc(text)
        self.assertIn("300 total", result)
        self.assertIn("wc entries omitted", result)


class CatLike(unittest.TestCase):
    def test_passthrough(self):
        text = "anything\nwhatever\n"
        self.assertEqual(filter_cat_like(text), text)


class Dispatch(unittest.TestCase):
    def _name(self, cmd):
        fn = find_cmd_filter(cmd)
        return fn.__name__ if fn else None

    def test_find_routed(self):
        self.assertEqual(self._name("find . -name '*.py'"), "filter_find")

    def test_grep_routed(self):
        self.assertEqual(self._name("grep -rn 'foo' src/"), "filter_grep")
        self.assertEqual(self._name("rg --no-heading foo"), "filter_grep")

    def test_ls_routed(self):
        self.assertEqual(self._name("ls -la"), "filter_ls")

    def test_tree_routed(self):
        self.assertEqual(self._name("tree -L 2 src/"), "filter_tree")

    def test_wc_routed(self):
        self.assertEqual(self._name("wc -l *.py"), "filter_wc")

    def test_cat_routed(self):
        self.assertEqual(self._name("cat /etc/hosts"), "filter_cat_like")
        self.assertEqual(self._name("head -n 50 file"), "filter_cat_like")
        self.assertEqual(self._name("tail -f log"), "filter_cat_like")

    def test_specific_wins_over_listing(self):
        # `cargo test` shouldn't route to ls/grep even though its output may
        # contain ls-shaped or grep-shaped lines.
        self.assertEqual(self._name("cargo test"), "filter_cargo_test")
        self.assertEqual(self._name("pytest tests/"), "filter_pytest_output")

    def test_pipe_routes_to_terminal_filter(self):
        # For `ls | grep foo` the stdout is grep's output, not ls's. The
        # listing block's registration order puts grep before ls so the
        # filter that actually matches the shape wins. Documented so a
        # future reorder doesn't silently flip behavior.
        self.assertEqual(self._name("ls | grep foo"), "filter_grep")


if __name__ == "__main__":
    unittest.main()
