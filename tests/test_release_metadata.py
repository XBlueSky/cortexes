"""The published `cortex-vec` version must track the source in this repo.

PR #20 shipped source changes to `cortex_vec` (the Weekly removal touched
`cli.py` and `parser.py`) while `pyproject.toml` still read 0.7.0 and the PR
described the package as "unchanged". A plugin release that leaves the CLI
behind means `uv tool install cortex-vec` keeps handing users the retired
`--type weekly` help — the removal would be complete in the repo and invisible
on their machine.

These tests keep the version, the tag the publish workflow expects, and the
upgrade step the READMEs document from drifting apart.

Run with: python3 -m pytest tests/test_release_metadata.py
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "cortex-vec" / "pyproject.toml"


def _version() -> str:
    m = re.search(r'^version = "([^"]+)"$', PYPROJECT.read_text(encoding="utf-8"), re.M)
    assert m, "cortex-vec/pyproject.toml has no version"
    return m.group(1)


class ReleaseMetadata(unittest.TestCase):
    def test_version_is_parseable(self):
        self.assertRegex(_version(), r"^\d+\.\d+\.\d+$")

    def test_readmes_name_the_version_they_tell_users_to_upgrade_to(self):
        version = _version()
        for name in ("README.md", "README.zh-TW.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(
                "uv tool upgrade cortex-vec", text,
                f"{name}'s upgrade path must tell users to upgrade the CLI",
            )
            self.assertIn(
                f"cortex-vec` {version}", text,
                f"{name} names a cortex-vec version other than pyproject's {version}",
            )

    def test_publish_workflow_still_gates_on_the_pyproject_version(self):
        """The tag→version check is what makes the bump meaningful."""
        wf = (ROOT / ".github/workflows/publish-cortex-vec.yml").read_text(encoding="utf-8")
        self.assertIn("cortex-vec-v", wf)
        self.assertIn("pyproject.toml", wf)
        self.assertIn("!=", wf, "the workflow must fail when tag and version disagree")


if __name__ == "__main__":
    unittest.main()
