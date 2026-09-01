"""Weekly/ is no longer a Cortexes content type.

`classify_path` used to map `Weekly/` to an active `weekly` type, which is
what made `--type weekly` look like a real filter. Removing that branch is the
whole change: a leftover `Weekly/` directory stays on disk and simply falls
through to `unknown`, like any other unrecognised top-level folder. Indexing
never scanned it (rebuild walks only Notes/ and Projects/), so nobody's
existing index changes.
"""
import sys

import pytest

from cortex_vec import cli
from cortex_vec.parser import classify_path


def test_weekly_path_is_not_an_active_content_type():
    doc_type, category = classify_path("Weekly/2026-W12.md")
    assert doc_type != "weekly"
    assert (doc_type, category) == ("unknown", "")


def test_still_recognised_types_are_untouched():
    assert classify_path("Notes/Nginx/ssl.md") == ("note", "Nginx")
    assert classify_path("Projects/acme/plan.md") == ("project", "acme")
    assert classify_path("Projects/_archive/old.md") == ("archive", "")
    assert classify_path("Raw/2026-09-01.md") == ("raw", "")


def test_search_help_does_not_advertise_a_weekly_filter(monkeypatch, capsys):
    """The real `cortex-vec search --help` text, not a copy of it."""
    monkeypatch.setattr(sys, "argv", ["cortex-vec", "search", "--help"])
    with pytest.raises(SystemExit):
        cli.main()
    out = capsys.readouterr().out.lower()
    assert "--type" in out, out
    assert "weekly" not in out, out
    assert "note/project" in out, out
