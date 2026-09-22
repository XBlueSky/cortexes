"""normalize_line_breaks: Raw files must contain exactly one kind of line break.

Bare "\r" from terminal progress output (and the other boundaries Python's
str.splitlines() recognises) make text-mode readers disagree with git about
line counts; git hosting pre-receive hooks that parse the diff then reject the
push. The filter rewrites them once, at capture time.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "hooks" / "scripts"
_SCRIPT = _SCRIPTS_DIR / "filter-transcript.py"
# the script imports its sibling modules (log_dedup, ...) by bare name
sys.path.insert(0, str(_SCRIPTS_DIR))
_spec = importlib.util.spec_from_file_location("filter_transcript", _SCRIPT)
filter_transcript = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(filter_transcript)
normalize_line_breaks = filter_transcript.normalize_line_breaks


class NormalizeLineBreaksTest(unittest.TestCase):
    def test_crlf_collapses_to_lf(self):
        self.assertEqual(normalize_line_breaks("a\r\nb\r\n"), "a\nb\n")

    def test_bare_cr_becomes_lf(self):
        # progress-bar redraws: one line per redraw, nothing lost
        self.assertEqual(
            normalize_line_breaks("Reading database ... 5%\rReading database ... 10%\r"),
            "Reading database ... 5%\nReading database ... 10%\n",
        )

    def test_other_splitlines_boundaries(self):
        for ch in ("\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", " ", " "):
            with self.subTest(repr(ch)):
                self.assertEqual(normalize_line_breaks(f"x{ch}y"), "x\ny")

    def test_plain_lf_text_is_untouched(self):
        text = "line 1\nline 2\n\n中文 — em dash, tabs\tkept\n"
        self.assertEqual(normalize_line_breaks(text), text)

    def test_result_has_single_line_break_kind(self):
        text = "a\r\nb\rc\x0cd e"
        out = normalize_line_breaks(text)
        self.assertEqual(out.splitlines(), out.split("\n"))
        self.assertEqual(out, "a\nb\nc\nd\ne")


if __name__ == "__main__":
    unittest.main()
