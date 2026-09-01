"""Two contracts in `cortex-query`'s SKILL.md that live testing showed matter.

**Score semantics.** `fusion.py` reports `score` as the vector cosine
similarity only, so a hit that came from the BM25 or graph stream and is not
in the vector index scores exactly `0.0` — by design, so distill/broadcast's
absolute-threshold dedup keeps working. The skill's threshold table read
"< 0.60: weak match, mention only if nothing better found", which meant that
in the BM25-only mode 2.0.0 explicitly advertises as real retrieval, *every*
hit was to be treated as barely worth mentioning. A live run reproduced it:
the model found the right page, saw `score 0.00`, and hedged.

**Vault resolution.** `CORTEX_VAULT_PATH` is honoured by `session-start-inject.sh`
and the `takeoff.sh` helper, but not by the write side or the index paths.
The skill must not reintroduce it as a read-side override.

Run with: python3 -m pytest tests/test_query_skill_contract.py
"""
from __future__ import annotations

import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "cortex-query" / "SKILL.md"


class QuerySkillContract(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    def test_zero_score_is_documented_as_no_cosine_not_a_weak_match(self):
        self.assertIn("vector cosine similarity", self.text)
        self.assertRegex(
            self.text, r"(?s)`0\.0`.{0,200}not a weak match|not\* a weak match",
        )
        self.assertIn("Trust the **order**", self.text)

    def test_bm25_only_mode_is_named_as_real_retrieval(self):
        self.assertRegex(
            self.text, r"(?is)without `OPENAI_API_KEY`.{0,240}real search",
            "the skill must say an all-0.0 scoreboard is BM25 mode, not failure",
        )

    def test_layer_2_is_not_gated_on_the_score_threshold(self):
        """`all scores < 0.60` was always true in BM25-only mode."""
        self.assertNotIn("If Layer 1 returns no strong results (all scores < 0.60)", self.text)

    def test_vault_resolution_stays_on_config_json(self):
        self.assertIn("Do **not** read `CORTEX_VAULT_PATH` here", self.text)
        self.assertIn("~/.cortex/config.json", self.text)


if __name__ == "__main__":
    unittest.main()
