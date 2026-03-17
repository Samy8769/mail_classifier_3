"""Tests for keyword_engine module (pure-Python Aho-Corasick)."""

import test_bootstrap  # noqa: F401 — stubs win32com
import unittest
from mail_classifier.keyword_engine import KeywordEngine


class TestKeywordEngine(unittest.TestCase):
    def setUp(self):
        self.engine = KeywordEngine()
        self.engine.build_automaton("type_mail", {
            "T_Qualite": [
                {"keyword": "qualite", "weight": 1.0},
                {"keyword": "non-conformite", "weight": 1.2},
            ],
            "T_Projet": [
                {"keyword": "projet", "weight": 1.0},
            ],
        })

    def test_basic_matching(self):
        hits = self.engine.search("type_mail", "rapport qualite projet")
        tag_names = {h.tag_name for h in hits}
        self.assertIn("T_Qualite", tag_names)
        self.assertIn("T_Projet", tag_names)

    def test_accent_insensitive(self):
        hits = self.engine.search("type_mail", "rapport qualité du projet")
        tag_names = {h.tag_name for h in hits}
        self.assertIn("T_Qualite", tag_names)

    def test_case_insensitive(self):
        hits = self.engine.search("type_mail", "QUALITE DU PROJET")
        tag_names = {h.tag_name for h in hits}
        self.assertIn("T_Qualite", tag_names)
        self.assertIn("T_Projet", tag_names)

    def test_no_match(self):
        hits = self.engine.search("type_mail", "bonjour monde")
        self.assertEqual(len(hits), 0)

    def test_missing_axis(self):
        hits = self.engine.search("nonexistent_axis", "qualite")
        self.assertEqual(len(hits), 0)

    def test_multiple_hits_same_tag(self):
        hits = self.engine.search("type_mail", "qualite et non-conformite")
        qualite_hits = [h for h in hits if h.tag_name == "T_Qualite"]
        self.assertEqual(len(qualite_hits), 2)

    def test_weight_preserved(self):
        hits = self.engine.search("type_mail", "non-conformite")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].weight, 1.2)

    def test_has_automaton(self):
        self.assertTrue(self.engine.has_automaton("type_mail"))
        self.assertFalse(self.engine.has_automaton("unknown"))

    def test_shared_keyword_across_tags(self):
        """Two tags can share a keyword."""
        engine = KeywordEngine()
        engine.build_automaton("test", {
            "TAG_A": [{"keyword": "commun", "weight": 1.0}],
            "TAG_B": [{"keyword": "commun", "weight": 0.5}],
        })
        hits = engine.search("test", "mot commun ici")
        tag_names = {h.tag_name for h in hits}
        self.assertIn("TAG_A", tag_names)
        self.assertIn("TAG_B", tag_names)


if __name__ == '__main__':
    unittest.main()
