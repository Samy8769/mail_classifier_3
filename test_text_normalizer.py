"""Tests for text_normalizer module."""

import test_bootstrap  # noqa: F401 — stubs win32com
import unittest
from mail_classifier.text_normalizer import normalize, normalize_for_regex, strip_accents


class TestStripAccents(unittest.TestCase):
    def test_french_accents(self):
        self.assertEqual(strip_accents("qualité"), "qualite")
        self.assertEqual(strip_accents("référence"), "reference")
        self.assertEqual(strip_accents("à côté"), "a cote")

    def test_no_accents(self):
        self.assertEqual(strip_accents("hello world"), "hello world")

    def test_empty(self):
        self.assertEqual(strip_accents(""), "")


class TestNormalize(unittest.TestCase):
    def test_lowercase(self):
        self.assertEqual(normalize("QUALITE"), "qualite")

    def test_accent_stripping(self):
        self.assertEqual(normalize("Qualité"), "qualite")

    def test_whitespace_collapse(self):
        self.assertEqual(normalize("hello   world\n\tfoo"), "hello world foo")

    def test_abbreviation_expansion(self):
        result = normalize("voir pj ci-joint")
        self.assertIn("piece jointe", result)

    def test_keep_accents(self):
        result = normalize("Qualité", keep_accents=True)
        self.assertEqual(result, "qualité")

    def test_no_abbreviation_expansion(self):
        result = normalize("voir pj", expand_abbreviations=False)
        self.assertIn("pj", result)

    def test_empty_string(self):
        self.assertEqual(normalize(""), "")

    def test_none_returns_empty(self):
        self.assertEqual(normalize(None), "")


class TestNormalizeForRegex(unittest.TestCase):
    def test_preserves_case(self):
        self.assertEqual(normalize_for_regex("CAM001"), "CAM001")

    def test_collapses_whitespace(self):
        self.assertEqual(normalize_for_regex("hello   world"), "hello world")

    def test_empty(self):
        self.assertEqual(normalize_for_regex(""), "")

    def test_none(self):
        self.assertEqual(normalize_for_regex(None), "")


if __name__ == '__main__':
    unittest.main()
