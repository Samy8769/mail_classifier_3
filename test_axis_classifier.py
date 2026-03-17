"""Tests for axis_classifier module — integration of the full per-axis pipeline."""

import test_bootstrap  # noqa: F401 — stubs win32com
import unittest
from unittest.mock import MagicMock
from mail_classifier.keyword_engine import KeywordEngine
from mail_classifier.regex_engine import RegexEngine
from mail_classifier.scorer import HeuristicScorer
from mail_classifier.axis_classifier import AxisClassifier
from mail_classifier.classification_pipeline import build_llm_prompt


class TestAxisClassifierLocal(unittest.TestCase):
    """Test local-only classification (no LLM)."""

    def setUp(self):
        self.kw_engine = KeywordEngine()
        self.kw_engine.build_automaton("type_mail", {
            "T_Qualite": [
                {"keyword": "qualite", "weight": 1.0},
                {"keyword": "non-conformite", "weight": 1.2},
            ],
            "T_Projet": [
                {"keyword": "projet", "weight": 1.0},
            ],
            "T_Technique": [
                {"keyword": "technique", "weight": 1.0},
            ],
        })
        self.rx_engine = RegexEngine()
        self.scorer = HeuristicScorer({
            "type_mail": {
                "confidence_threshold": 0.7,
                "ambiguity_margin": 0.15,
                "min_hits_for_confidence": 1,
            },
        })

    def test_clear_local_decision(self):
        classifier = AxisClassifier(
            axis_name="type_mail",
            keyword_engine=self.kw_engine,
            regex_engine=self.rx_engine,
            scorer=self.scorer,
            valid_tags={"T_Qualite", "T_Projet", "T_Technique"},
        )
        result = classifier.classify("rapport qualite non-conformite important")
        self.assertIn("T_Qualite", result.selected_tags)
        self.assertEqual(result.method, "local")
        self.assertGreater(result.confidence, 0.7)

    def test_no_match_without_llm(self):
        classifier = AxisClassifier(
            axis_name="type_mail",
            keyword_engine=self.kw_engine,
            regex_engine=self.rx_engine,
            scorer=self.scorer,
            valid_tags={"T_Qualite", "T_Projet"},
        )
        result = classifier.classify("bonjour monde rien a voir")
        # No candidates, no LLM -> empty or no_match
        self.assertEqual(result.method, "no_match")
        self.assertEqual(result.selected_tags, [])


class TestAxisClassifierWithLLM(unittest.TestCase):
    """Test classification with mocked LLM."""

    def setUp(self):
        self.kw_engine = KeywordEngine()
        self.kw_engine.build_automaton("type_mail", {
            "T_Qualite": [
                {"keyword": "qualite", "weight": 1.0},
            ],
            "T_Technique": [
                {"keyword": "technique", "weight": 1.0},
            ],
        })
        self.rx_engine = RegexEngine()
        self.scorer = HeuristicScorer({
            "type_mail": {
                "confidence_threshold": 0.7,
                "ambiguity_margin": 0.15,
                "min_hits_for_confidence": 1,
            },
        })

    def test_llm_called_when_ambiguous(self):
        mock_api = MagicMock()
        mock_api.call_paradigm.return_value = "T_Technique"

        classifier = AxisClassifier(
            axis_name="type_mail",
            keyword_engine=self.kw_engine,
            regex_engine=self.rx_engine,
            scorer=self.scorer,
            api_client=mock_api,
            valid_tags={"T_Qualite", "T_Technique"},
            llm_prompt_builder=build_llm_prompt,
        )
        result = classifier.classify("sujet technique qualite melange")
        mock_api.call_paradigm.assert_called_once()
        self.assertIn("T_Technique", result.selected_tags)

    def test_llm_error_falls_back_to_local(self):
        mock_api = MagicMock()
        mock_api.call_paradigm.side_effect = Exception("API down")

        classifier = AxisClassifier(
            axis_name="type_mail",
            keyword_engine=self.kw_engine,
            regex_engine=self.rx_engine,
            scorer=self.scorer,
            api_client=mock_api,
            valid_tags={"T_Qualite", "T_Technique"},
            llm_prompt_builder=build_llm_prompt,
        )
        result = classifier.classify("sujet technique qualite melange")
        # Should fall back to local candidate
        self.assertEqual(result.method, "local_fallback_on_error")
        self.assertGreater(len(result.selected_tags), 0)


class TestAxisClassifierWithRegex(unittest.TestCase):
    """Test regex-dominant axis (equipement_designation)."""

    def setUp(self):
        self.kw_engine = KeywordEngine()
        self.kw_engine.build_automaton("equipement_designation", {
            "EQ_CAM001": [{"keyword": "cam001", "weight": 1.0}],
            "EQ_MV2": [{"keyword": "mv2", "weight": 1.0}],
        })
        self.rx_engine = RegexEngine()
        self.rx_engine.register_patterns("equipement_designation", [
            {
                "name": "cam_serial",
                "pattern": r"\b(CAM\d{3,4})\b",
                "tag_template": "EQ_{0}",
                "weight": 2.5,
                "flags": "IGNORECASE",
            },
        ])
        self.scorer = HeuristicScorer({
            "equipement_designation": {
                "keyword_weight_multiplier": 1.0,
                "regex_weight_multiplier": 2.0,
                "confidence_threshold": 0.65,
                "ambiguity_margin": 0.1,
                "min_hits_for_confidence": 1,
            },
        })

    def test_regex_and_keyword_combined(self):
        classifier = AxisClassifier(
            axis_name="equipement_designation",
            keyword_engine=self.kw_engine,
            regex_engine=self.rx_engine,
            scorer=self.scorer,
            valid_tags={"EQ_CAM001", "EQ_MV2"},
            max_tags=3,
        )
        result = classifier.classify("Le modele CAM001 presente un defaut. Verifier MV2.")
        self.assertIn("EQ_CAM001", result.selected_tags)
        self.assertIn("EQ_MV2", result.selected_tags)
        self.assertEqual(result.method, "local")


if __name__ == '__main__':
    unittest.main()
