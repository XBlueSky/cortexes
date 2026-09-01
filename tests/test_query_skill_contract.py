"""Contracts in `cortex-query`'s SKILL.md that live testing showed matter.

**Score semantics.** `fusion.search()` reports `score` as the vector cosine
similarity only — by design, so distill/broadcast's absolute-threshold dedup
keeps working. It is not overall hybrid confidence, and it is not what
ordered the list: RRF fusion (plus rerank) decides that. Two ways the skill
got this wrong:

  - A threshold table reading "< 0.60: Weak match — mention only if nothing
    better found" turned a *semantic-overlap* number into a verdict on
    relevance, so any high-ranked BM25 or graph hit with a low or zero cosine
    was to be buried. In BM25-only mode that is every result.
  - `0.0` was described as "not in the vector index". `_vector_stream` returns
    only its own top-n for the query, so an indexed page that merely placed
    lower in that one stream also reports `0.0`. The number cannot establish
    a document's index membership, and cannot establish BM25-only mode either.

**Vault resolution.** `CORTEX_VAULT_PATH` is honoured by
`session-start-inject.sh` and the `takeoff.sh` helper, but not by the write
side or the index paths. The skill must not reintroduce it as a read-side
override.

Run with: python3 -m pytest tests/test_query_skill_contract.py
"""
from __future__ import annotations

import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "cortex-query" / "SKILL.md"


class QuerySkillContract(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    # --- what `score` is, and is not -----------------------------------
    def test_score_is_named_as_cosine_only_not_hybrid_confidence(self):
        self.assertIn("vector cosine similarity only", self.text)
        self.assertRegex(
            self.text, r"(?i)not\W{0,4}overall hybrid confidence",
            "the skill must say `score` is not overall hybrid confidence",
        )

    def test_thresholds_are_semantic_overlap_bands_only(self):
        self.assertIn("semantic overlap", self.text)
        self.assertNotIn(
            "Score < 0.60: Weak match — mention only if nothing better found",
            self.text,
            "a cosine band must not be restated as a relevance verdict",
        )
        self.assertNotRegex(
            self.text, r"(?i)weak match\s*[—-]\s*mention only",
            "no threshold may demote a hit to 'mention only if nothing better'",
        )

    def test_relevance_follows_the_returned_order(self):
        self.assertRegex(
            self.text, r"(?i)relevance follows the returned order",
            "final relevance must be driven by the fusion/rerank order",
        )
        # The fields the CLI actually returns — not "matched text", which it
        # does not; excerpts come from the Layer 2 grep supplement.
        for field in ("`title`", "`category`", "`tags`", "`summary`"):
            self.assertIn(field, self.text, f"Layer 1 guidance must name {field}")
        self.assertRegex(
            self.text, r"(?is)Layer 1\s*\n?returns no excerpt",
            "the skill must say Layer 1 returns no excerpt",
        )

    def test_high_ranked_low_cosine_hits_are_not_demoted(self):
        self.assertRegex(
            self.text,
            r"(?is)never demote a high-ranked BM25 or graph result solely because"
            r".{0,60}cosine is\s*\n?low or zero",
            "the skill must forbid demoting a high-ranked hit for a low/zero cosine",
        )

    # --- what 0.0 does and does not prove ------------------------------
    def test_zero_is_described_by_provenance_not_by_index_membership(self):
        self.assertRegex(
            self.text,
            r"(?is)received no score from the current\s*\n?vector result stream",
            "0.0 must be described as 'no score from the current vector stream'",
        )
        self.assertNotIn(
            "not in the vector index", self.text,
            "0.0 does not establish that a page is absent from the vector index",
        )

    def test_retrieval_mode_is_not_inferred_from_zero(self):
        self.assertRegex(
            self.text, r"(?is)do not infer BM25-only mode from `0\.0` alone",
            "the skill must forbid inferring the retrieval mode from 0.0 alone",
        )
        self.assertRegex(
            self.text, r"(?is)only when you know that independently",
            "BM25-only may be named only on independent evidence",
        )

    def test_layer_2_is_not_gated_on_the_score_threshold(self):
        """`all scores < 0.60` was always true in BM25-only mode."""
        self.assertNotIn("If Layer 1 returns no strong results (all scores < 0.60)", self.text)
        self.assertRegex(
            self.text, r"(?is)never from the score column alone",
            "Layer 2's trigger must not be a score threshold",
        )

    # --- vault resolution ----------------------------------------------
    def test_vault_resolution_stays_on_config_json(self):
        self.assertIn("Do **not** read `CORTEX_VAULT_PATH` here", self.text)
        self.assertIn("~/.cortex/config.json", self.text)


if __name__ == "__main__":
    unittest.main()
