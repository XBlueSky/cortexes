"""User-facing docs must not make absolute claims about what reaches Anthropic.

Cortexes runs *inside* Claude Code. Vault content a command or skill loads —
and the topic metadata SessionStart injects — is ordinary session context, so
it is processed by Anthropic under the user's own account. `CORTEX_NO_CLASSIFIER`
only stops the transcript filter's extra nested classifier calls; it has no
bearing on the session itself.

The env-var tables said the opposite ("Nothing is sent to Anthropic") long
after PRIVACY.md had been corrected, which is the worst place for it: a table
row is what people actually read before trusting a flag. These tests keep the
absolute phrasing from coming back anywhere user-facing.

Run with: python3 -m pytest tests/test_privacy_claims.py
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DOCS = [
    "README.md", "README.zh-TW.md",
    "PRIVACY.md", "PRIVACY.zh-TW.md",
    "SECURITY.md", "SECURITY.zh-TW.md",
    ".cc-marketspec/entries/plugin-cortexes.yaml",
]

# Claims that are simply false. No context makes them true, so ban the string.
BANNED = [
    "Nothing is sent to Anthropic",
    "nothing is sent to anthropic",
    "不會有任何資料送往 Anthropic",
    "不會有任何資料送往Anthropic",
    "fully offline",
]

# Claims that are fine *only* as something the text goes on to deny.
NEEDS_NEGATION = {
    "nothing leaves your machine": ("not the same", "is not", "isn't"),
    "沒有任何資料離開": ("不是", "並非"),
}


def _docs():
    return [(name, (ROOT / name).read_text(encoding="utf-8")) for name in DOCS]


class PrivacyClaims(unittest.TestCase):
    def test_every_doc_exists(self):
        """Guard the guard: a renamed file would make the sweep vacuous."""
        for name in DOCS:
            self.assertTrue((ROOT / name).is_file(), f"{name} is missing")

    def test_no_absolute_anthropic_claim(self):
        for name, text in _docs():
            lowered = text.lower()
            for phrase in BANNED:
                self.assertNotIn(
                    phrase.lower(), lowered,
                    f"{name} claims {phrase!r} — vault content and SessionStart "
                    f"metadata reach Anthropic as ordinary session context",
                )

    def test_offline_style_claims_are_only_ever_denied(self):
        for name, text in _docs():
            for line in text.splitlines():
                low = line.lower()
                for phrase, markers in NEEDS_NEGATION.items():
                    if phrase in low:
                        self.assertTrue(
                            any(m in low for m in markers),
                            f"{name}: {phrase!r} must appear only as a claim the "
                            f"text denies, not as a promise — {line.strip()!r}",
                        )

    def test_no_classifier_row_is_scoped(self):
        """The env-var tables must say what the flag actually covers."""
        for name, marker in (("README.md", "only"), ("README.zh-TW.md", "只")):
            row = next(
                line for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
                if line.startswith("| `CORTEX_NO_CLASSIFIER`")
            )
            self.assertIn(marker, row.lower() if marker == "only" else row, row)
            self.assertIn("classifier", row.lower(), row)


if __name__ == "__main__":
    unittest.main()
