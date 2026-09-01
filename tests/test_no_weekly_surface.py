"""Weekly/ is retired: nothing user-facing may advertise or create it.

Cortexes' vault taxonomy is Raw/, Notes/, Projects/. The `cortex-weekly`
skill and its command went away earlier; what lingered was the *taxonomy*
—`Weekly/` in genesis's mkdir list, a `weekly` value in the `--type` filter,
"Weekly reports" in the vault description — so the plugin still told users
about a content type it no longer produced, indexed, or searched.

These tests pin the four surfaces that carried it: the command files, the
skill files, `cortex-vec`'s search help, and genesis's vault-setup steps.

Deliberately NOT covered:
  - CHANGELOG.md — history describes the feature as it existed; that stays.
  - the `週報`/`weekly report` synonym pair — ordinary words that can appear
    inside an ordinary Note. A synonym is vocabulary, not a content type.
  - .gitignore's `Weekly/` — a guard against committing vault data, which
    still matters for anyone whose vault has the leftover directory.

Run with: python3 -m pytest tests/test_no_weekly_surface.py
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENESIS = ROOT / "commands" / "genesis.md"
CLI = ROOT / "cortex-vec" / "src" / "cortex_vec" / "cli.py"


def _surface_files() -> list[Path]:
    return sorted(ROOT.glob("commands/*.md")) + sorted(ROOT.glob("skills/*/SKILL.md"))


class NoWeeklySurface(unittest.TestCase):
    def test_the_surface_set_is_not_empty(self):
        """Guard the guard: a bad glob would make every test below vacuous."""
        files = _surface_files()
        self.assertGreaterEqual(len(files), 10, [str(f) for f in files])
        self.assertIn(GENESIS, files)

    def test_no_command_or_skill_mentions_weekly(self):
        """Genesis is the sole exception — it has to name what it won't create."""
        for path in _surface_files():
            if path == GENESIS:
                continue
            hits = [
                line for line in path.read_text(encoding="utf-8").splitlines()
                if "weekly" in line.lower()
            ]
            self.assertEqual(
                hits, [], f"{path.relative_to(ROOT)} still advertises Weekly: {hits}"
            )

    def test_genesis_does_not_create_weekly(self):
        text = GENESIS.read_text(encoding="utf-8")
        self.assertNotRegex(
            text, r"(?im)^\s*-\s*`?Weekly/`?\s*$",
            "genesis still lists Weekly/ as a directory to create",
        )
        self.assertRegex(
            text, r"(?i)do \*\*not\*\* create `Weekly/`",
            "genesis must say explicitly that Weekly/ is not created",
        )

    def test_genesis_never_deletes_an_existing_weekly(self):
        text = GENESIS.read_text(encoding="utf-8")
        self.assertRegex(
            text, r"(?i)never move, rewrite,\s*\n?or delete them",
            "genesis must promise not to touch a user's existing Weekly/",
        )
        self.assertRegex(
            text, r"(?i)moved into `Notes/` or\s*\n?`Projects/`",
            "genesis must tell the user where to move content they still want",
        )

    def test_genesis_vault_detection_uses_the_live_taxonomy(self):
        """Weekly/ must not count as proof that a directory is a cortex vault."""
        for line in GENESIS.read_text(encoding="utf-8").splitlines():
            if "recognize it as an existing vault" in line:
                self.assertNotIn("Weekly", line, line)
                self.assertIn("Notes/", line, line)
                return
        self.fail("genesis lost its existing-vault detection step")

    def test_cli_search_type_help_offers_no_weekly_filter(self):
        """The help string users read when they run `cortex-vec search --help`.

        `cortex-vec/tests/test_no_weekly_type.py` asserts the same thing
        against argparse's rendered output; this one keeps the plugin's own
        gate honest without importing the package.
        """
        for line in CLI.read_text(encoding="utf-8").splitlines():
            if '"--type"' in line:
                self.assertNotIn("weekly", line.lower(), line)
                self.assertIn("note/project", line, line)
                return
        self.fail("cortex-vec search lost its --type argument")


if __name__ == "__main__":
    unittest.main()
