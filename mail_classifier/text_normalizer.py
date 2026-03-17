"""
Text normalization for keyword and regex matching.
Normalizes French business email text: accents, case, whitespace, abbreviations.
"""

import re
import unicodedata


# Common French business abbreviations
_ABBREVIATIONS = {
    "n/r": "notre reference",
    "v/r": "votre reference",
    "réf.": "reference",
    "ref.": "reference",
    "pj": "piece jointe",
    "p.j.": "piece jointe",
}


def strip_accents(text: str) -> str:
    """Remove accents from Unicode text (e.g. é -> e, à -> a)."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def normalize(text: str, keep_accents: bool = False,
              expand_abbreviations: bool = True) -> str:
    """
    Normalize text for Aho-Corasick keyword matching.

    Steps: lowercase -> expand abbreviations -> strip accents -> collapse whitespace.

    Args:
        text: Raw email text.
        keep_accents: If True, preserve accented characters.
        expand_abbreviations: If True, expand known FR abbreviations.

    Returns:
        Normalized text string.
    """
    if not text:
        return ""

    result = text.lower()

    if expand_abbreviations:
        for abbr, expansion in _ABBREVIATIONS.items():
            result = result.replace(abbr, expansion)

    if not keep_accents:
        result = strip_accents(result)

    result = re.sub(r'\s+', ' ', result).strip()
    return result


def normalize_for_regex(text: str) -> str:
    """
    Light normalization for regex matching.
    Preserves case and special characters; only collapses whitespace.
    """
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()
