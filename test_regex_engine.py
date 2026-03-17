"""Tests for regex_engine module."""

import test_bootstrap  # noqa: F401 — stubs win32com
import unittest
from mail_classifier.regex_engine import RegexEngine


class TestRegexEngine(unittest.TestCase):
    def setUp(self):
        self.engine = RegexEngine()
        self.engine.register_patterns("equipement_designation", [
            {
                "name": "cam_serial",
                "pattern": r"\b(CAM\d{3,4})\b",
                "tag_template": "EQ_{0}",
                "weight": 2.5,
                "flags": "IGNORECASE",
            },
            {
                "name": "model_designation",
                "pattern": r"\b(?:modele|model)\s*:\s*([A-Z]{2,4}\d{1,4})\b",
                "tag_template": "EQ_{0}",
                "weight": 2.0,
                "flags": "IGNORECASE",
            },
        ])

    def test_serial_number_match(self):
        hits = self.engine.search("equipement_designation", "Verifier CAM001 urgent")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].tag_name, "EQ_CAM001")
        self.assertEqual(hits[0].matched_text, "CAM001")
        self.assertEqual(hits[0].weight, 2.5)

    def test_case_insensitive(self):
        hits = self.engine.search("equipement_designation", "verifier cam002")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].tag_name, "EQ_cam002")

    def test_multiple_matches(self):
        hits = self.engine.search("equipement_designation", "CAM001 et CAM002 a verifier")
        self.assertEqual(len(hits), 2)
        tags = {h.tag_name for h in hits}
        self.assertIn("EQ_CAM001", tags)
        self.assertIn("EQ_CAM002", tags)

    def test_valid_tags_filter(self):
        valid = {"EQ_CAM001"}
        hits = self.engine.search("equipement_designation", "CAM001 et CAM999", valid_tags=valid)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].tag_name, "EQ_CAM001")

    def test_no_match(self):
        hits = self.engine.search("equipement_designation", "rien a voir ici")
        self.assertEqual(len(hits), 0)

    def test_missing_axis(self):
        hits = self.engine.search("nonexistent", "CAM001")
        self.assertEqual(len(hits), 0)

    def test_model_designation_pattern(self):
        hits = self.engine.search("equipement_designation", "modele: FM12 a verifier")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].tag_name, "EQ_FM12")

    def test_has_patterns(self):
        self.assertTrue(self.engine.has_patterns("equipement_designation"))
        self.assertFalse(self.engine.has_patterns("unknown"))

    def test_static_tag_name(self):
        """Test pattern with static tag_name instead of tag_template."""
        engine = RegexEngine()
        engine.register_patterns("anomalies", [
            {
                "name": "anomaly_fixed",
                "pattern": r"\bAN-\d{3}\b",
                "tag_name": "AN_GENERIC",
                "weight": 1.5,
            },
        ])
        hits = engine.search("anomalies", "Voir AN-042")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].tag_name, "AN_GENERIC")


if __name__ == '__main__':
    unittest.main()
