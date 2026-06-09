"""Tests for rtk_filter fail-open degradation.

rtk_filter.py needs a TOML parser: `tomllib` (Python 3.11+), falling back to
`tomli`, and finally to None when neither is importable. When no parser is
available (e.g. the SessionEnd hook launched under an ambient Python < 3.11),
load_filters() must degrade to "no filters" — tool output is kept verbatim —
rather than crashing the whole filter-transcript pipeline.

Run with: python3 -m unittest tests.test_rtk_filter
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

import rtk_filter  # noqa: E402


class LoadFiltersFailOpen(unittest.TestCase):
    """load_filters must not crash when no TOML parser is available."""

    def setUp(self) -> None:
        self._saved_parser = rtk_filter.tomllib
        rtk_filter.tomllib = None  # simulate Python < 3.11 with no tomli

    def tearDown(self) -> None:
        rtk_filter.tomllib = self._saved_parser

    def test_returns_no_filters_when_parser_missing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "git.toml").write_text(
                '[filters.git]\nmatch_command = "git"\n'
            )
            # Must NOT raise. Degrade to an empty filter set so callers keep
            # tool output verbatim instead of the pipeline blowing up.
            self.assertEqual(rtk_filter.load_filters(Path(d)), [])


if __name__ == "__main__":
    unittest.main()
