"""Tests for scorer module."""

import test_bootstrap  # noqa: F401 — stubs win32com
import unittest
from mail_classifier.scorer import HeuristicScorer
from mail_classifier.keyword_engine import KeywordHit
from mail_classifier.regex_engine import RegexHit


class TestHeuristicScorer(unittest.TestCase):
    def setUp(self):
        self.scorer = HeuristicScorer({
            "type_mail": {
                "keyword_weight_multiplier": 1.0,
                "regex_weight_multiplier": 1.5,
                "confidence_threshold": 0.7,
                "ambiguity_margin": 0.15,
                "min_hits_for_confidence": 1,
            },
        })

    def test_clear_winner_no_llm(self):
        kw_hits = [
            KeywordHit("qualite", "T_Qualite", 10, 1.0),
            KeywordHit("non-conformite", "T_Qualite", 25, 1.2),
            KeywordHit("projet", "T_Projet", 40, 1.0),
        ]
        result = self.scorer.score("type_mail", kw_hits, [])
        self.assertFalse(result.needs_llm)
        self.assertEqual(result.candidates[0].tag_name, "T_Qualite")
        self.assertGreater(result.candidates[0].confidence, 0.7)

    def test_ambiguous_needs_llm(self):
        kw_hits = [
            KeywordHit("qualite", "T_Qualite", 10, 1.0),
            KeywordHit("technique", "T_Technique", 20, 1.0),
        ]
        result = self.scorer.score("type_mail", kw_hits, [])
        self.assertTrue(result.needs_llm)
        self.assertIn("ambiguous", result.llm_reason)

    def test_no_hits_needs_llm(self):
        result = self.scorer.score("type_mail", [], [])
        self.assertTrue(result.needs_llm)
        self.assertEqual(result.llm_reason, "no_candidates")

    def test_low_confidence_needs_llm(self):
        """Single hit below min_hits penalty still triggers LLM if threshold not met."""
        scorer = HeuristicScorer({
            "test": {
                "confidence_threshold": 0.9,
                "ambiguity_margin": 0.1,
                "min_hits_for_confidence": 3,
            }
        })
        kw_hits = [KeywordHit("kw", "TAG_A", 5, 0.5)]
        result = scorer.score("test", kw_hits, [])
        # Single hit with min_hits=3 -> confidence * 0.5 -> likely below 0.9
        self.assertTrue(result.needs_llm)

    def test_regex_hits_boost_score(self):
        kw_hits = [KeywordHit("cam001", "EQ_CAM001", 10, 1.0)]
        rx_hits = [RegexHit("cam_serial", "EQ_CAM001", "CAM001", 2.5, {})]
        result = self.scorer.score("type_mail", kw_hits, rx_hits)
        # EQ_CAM001 should have both kw and rx hits
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].keyword_hits, 1)
        self.assertEqual(result.candidates[0].regex_hits, 1)

    def test_candidates_sorted_by_confidence(self):
        kw_hits = [
            KeywordHit("a", "TAG_LOW", 5, 0.5),
            KeywordHit("b", "TAG_HIGH", 10, 2.0),
            KeywordHit("c", "TAG_HIGH", 15, 1.5),
        ]
        result = self.scorer.score("type_mail", kw_hits, [])
        self.assertEqual(result.candidates[0].tag_name, "TAG_HIGH")

    def test_default_config_for_unknown_axis(self):
        """Unknown axis uses default scoring params."""
        kw_hits = [
            KeywordHit("a", "TAG_A", 5, 2.0),
            KeywordHit("b", "TAG_B", 10, 0.1),
        ]
        result = self.scorer.score("unknown_axis", kw_hits, [])
        # Should still produce results with defaults
        self.assertGreater(len(result.candidates), 0)

    def test_sources_tracking(self):
        kw_hits = [KeywordHit("qualite", "T_Qualite", 10, 1.0)]
        rx_hits = [RegexHit("pattern1", "T_Qualite", "QUA", 1.5, {})]
        result = self.scorer.score("type_mail", kw_hits, rx_hits)
        sources = result.candidates[0].sources
        self.assertTrue(any("kw:" in s for s in sources))
        self.assertTrue(any("rx:" in s for s in sources))


if __name__ == '__main__':
    unittest.main()
