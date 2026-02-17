"""
Heuristic classification engine for multi-axis email categorization.

Architecture per axis:
  normalized text
  → Aho-Corasick (keywords + synonyms)
  → Regex (serial / part numbers only)
  → heuristic scoring
  → top-N candidates (max 3–5)
  → optional LLM arbitration if ambiguous
  → final value + confidence

Scoring weights
  subject match  : +3
  body match     : +1
  synonym bonus  : +2 (added on top of the base match score)
  repetitions    : cumulative (each occurrence adds its score)
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:
    import ahocorasick as _ac
    _AHOCORASICK_AVAILABLE = True
except ImportError:  # pragma: no cover
    _ac = None
    _AHOCORASICK_AVAILABLE = False

# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

SCORE_SUBJECT_MATCH = 3
SCORE_BODY_MATCH = 1
SCORE_SYNONYM_BONUS = 2   # extra points when the hit is a synonym


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

class TextNormalizer:
    """Normalize email text for keyword matching.

    Lowercases, strips combining diacritics (accents), and collapses
    whitespace so that French/English comparisons work uniformly.
    """

    def normalize(self, text: str) -> str:
        """Return normalized version of *text*.

        Args:
            text: Raw text (subject or body).

        Returns:
            Lowercase, accent-free, single-space-separated string.
        """
        if not text:
            return ''
        # Decompose into base characters + combining marks, then drop marks
        nfkd = unicodedata.normalize('NFKD', text.lower())
        ascii_text = ''.join(ch for ch in nfkd if not unicodedata.combining(ch))
        # Collapse any whitespace sequence into a single space
        return re.sub(r'\s+', ' ', ascii_text).strip()


# ---------------------------------------------------------------------------
# Aho-Corasick based keyword matcher
# ---------------------------------------------------------------------------

class AhoCorasickMatcher:
    """Multi-pattern matcher backed by Aho-Corasick (or regex fallback).

    Maps keywords and synonyms → (candidate_tag, is_synonym).
    The automaton is built once at construction; ``find_matches`` is O(n)
    in the text length.

    If *pyahocorasick* is not installed the class falls back to
    ``re.search`` with word-boundary anchors, which is slower but
    functionally equivalent.
    """

    def __init__(
        self,
        keyword_map: Dict[str, List[str]],
        synonym_map: Dict[str, List[str]],
    ) -> None:
        """
        Args:
            keyword_map: ``{candidate_tag: [keyword, ...]}``
            synonym_map: ``{candidate_tag: [synonym, ...]}``
                Synonyms receive ``SCORE_SYNONYM_BONUS`` on top of the
                regular match score.
        """
        self._normalizer = TextNormalizer()
        # Flat list of (normalized_pattern, candidate_tag, is_synonym)
        self._patterns: List[Tuple[str, str, bool]] = []

        for tag, keywords in keyword_map.items():
            for kw in keywords:
                norm = self._normalizer.normalize(kw)
                if norm:
                    self._patterns.append((norm, tag, False))

        for tag, synonyms in synonym_map.items():
            for syn in synonyms:
                norm = self._normalizer.normalize(syn)
                if norm:
                    self._patterns.append((norm, tag, True))

        self._automaton = None
        if _AHOCORASICK_AVAILABLE and self._patterns:
            self._build_automaton()
        else:
            self._compile_fallback()

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_automaton(self) -> None:
        """Build pyahocorasick automaton.

        Multiple patterns with the same normalized form are grouped so
        that one automaton hit can return multiple (tag, is_synonym) pairs.
        """
        # Group by keyword so the automaton stores a list of payloads
        kw_index: Dict[str, List[Tuple[str, bool]]] = {}
        for kw, tag, is_syn in self._patterns:
            kw_index.setdefault(kw, []).append((tag, is_syn))

        A = _ac.Automaton()
        for kw, payloads in kw_index.items():
            A.add_word(kw, (kw, payloads))
        A.make_automaton()
        self._automaton = A

    def _compile_fallback(self) -> None:
        """Compile regex patterns for environments without pyahocorasick."""
        self._fallback_regexes: List[Tuple[re.Pattern, str, bool]] = []
        for kw, tag, is_syn in self._patterns:
            # Use word-boundary anchors; for multi-word patterns \b on the
            # outer edges is sufficient.
            pattern = r'(?<![a-z0-9])' + re.escape(kw) + r'(?![a-z0-9])'
            try:
                compiled = re.compile(pattern)
                self._fallback_regexes.append((compiled, tag, is_syn))
            except re.error:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_matches(self, normalized_text: str) -> List[Tuple[str, str, bool]]:
        """Find all keyword/synonym occurrences in *normalized_text*.

        Args:
            normalized_text: Text already processed by :class:`TextNormalizer`.

        Returns:
            List of ``(matched_keyword, candidate_tag, is_synonym)`` tuples.
            A single keyword occurrence may appear multiple times if several
            candidates share it.
        """
        if self._automaton is not None:
            return self._find_matches_automaton(normalized_text)
        return self._find_matches_fallback(normalized_text)

    def _find_matches_automaton(self, text: str) -> List[Tuple[str, str, bool]]:
        results: List[Tuple[str, str, bool]] = []
        for end_idx, (kw, payloads) in self._automaton.iter(text):
            start_idx = end_idx - len(kw) + 1
            # Word-boundary check (avoid matching inside a longer token)
            before_ok = start_idx == 0 or not text[start_idx - 1].isalnum()
            after_ok = end_idx + 1 >= len(text) or not text[end_idx + 1].isalnum()
            # For very short keywords (≤2 chars) require strict boundaries
            if len(kw) <= 2 and not (before_ok and after_ok):
                continue
            # For longer keywords, at least one boundary must hold
            if len(kw) > 2 and not (before_ok or after_ok):
                continue
            for tag, is_syn in payloads:
                results.append((kw, tag, is_syn))
        return results

    def _find_matches_fallback(self, text: str) -> List[Tuple[str, str, bool]]:
        results: List[Tuple[str, str, bool]] = []
        for regex, tag, is_syn in self._fallback_regexes:
            for m in regex.finditer(text):
                results.append((m.group(0), tag, is_syn))
        return results


# ---------------------------------------------------------------------------
# Serial / part number extractor
# ---------------------------------------------------------------------------

class SerialNumberExtractor:
    """Extract serial and part numbers using regex patterns.

    Used **exclusively** for axes that deal with equipment designations
    (``EQ_`` prefix and any axis whose config supplies ``regex_patterns``).
    Never applied as a classification signal for other axes.
    """

    # Default patterns for aerospace serial/part numbers
    _DEFAULT_PATTERNS: List[str] = [
        r'\b[A-Z]{2,4}-\d{3,6}\b',           # CAM-001234, FM-0023
        r'\bSN[:\s]?\d{4,10}\b',              # SN:12345 or SN 12345
        r'\bPN[:\s]?[A-Z0-9\-]{4,15}\b',      # PN:ABC-1234
        r'\b\d{4}-[A-Z]{2,4}-\d{3,6}\b',      # 2024-CAM-001
        r'\b[A-Z]{2,3}\d{1,4}\b',               # FM1, FM12, CAM001, EM002
    ]

    def __init__(self, extra_patterns: Optional[List[str]] = None) -> None:
        patterns = self._DEFAULT_PATTERNS + (extra_patterns or [])
        self._regexes = [re.compile(p) for p in patterns]

    def extract(self, text: str) -> List[str]:
        """Return all serial/part numbers found in *text*.

        Args:
            text: Raw (non-normalized) email text.

        Returns:
            Sorted, deduplicated list of matched strings.
        """
        found: set = set()
        for regex in self._regexes:
            for m in regex.finditer(text):
                found.add(m.group(0))
        return sorted(found)


# ---------------------------------------------------------------------------
# Axis keyword configuration
# ---------------------------------------------------------------------------

@dataclass
class AxisKeywordConfig:
    """Complete keyword configuration for one classification axis.

    Attributes:
        axis_name:            Axis identifier (e.g. ``'type_mail'``).
        prefix:               Tag prefix (e.g. ``'T_'``).
        keyword_map:          ``{tag: [keyword, ...]}``.
        synonym_map:          ``{tag: [synonym, ...]}``.
                              Synonyms receive SCORE_SYNONYM_BONUS.
        regex_patterns:       Extra regex patterns for serial-number
                              extraction (leave empty for non-EQ axes).
        ambiguity_threshold:  If the score gap ratio between rank-1 and
                              rank-2 candidates is below this value the
                              result is flagged as ambiguous.
        min_score_threshold:  Candidates scoring at or below this value
                              are discarded.
        max_candidates:       Maximum number of candidates returned.
    """

    axis_name: str
    prefix: str
    keyword_map: Dict[str, List[str]]
    synonym_map: Dict[str, List[str]]
    regex_patterns: List[str] = field(default_factory=list)
    ambiguity_threshold: float = 0.15
    min_score_threshold: float = 0.0
    max_candidates: int = 5


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class CandidateMatch:
    """A single candidate with its accumulated score and debug hits."""

    tag: str
    score: float
    hits: List[str] = field(default_factory=list)   # e.g. ["subj:commande", "body:bdc"]


@dataclass
class AxisHeuristicResult:
    """Output of :class:`AxisHeuristicPipeline` for one axis.

    Attributes:
        axis_name:      Axis identifier.
        prefix:         Tag prefix.
        top_candidates: Ranked list of :class:`CandidateMatch`.
        is_ambiguous:   True when no clear winner was found.
        serial_numbers: Serial/part numbers extracted by regex (EQ_ axis).
        debug:          Raw scoring details for inspection.
    """

    axis_name: str
    prefix: str
    top_candidates: List[CandidateMatch]
    is_ambiguous: bool
    serial_numbers: List[str]
    debug: Dict = field(default_factory=dict)

    @property
    def best(self) -> Optional[CandidateMatch]:
        """Return the top-ranked candidate, or ``None``."""
        return self.top_candidates[0] if self.top_candidates else None

    @property
    def best_confidence(self) -> float:
        """Normalized confidence score (0–1) of the top candidate."""
        if not self.top_candidates:
            return 0.0
        total = sum(c.score for c in self.top_candidates)
        if total == 0.0:
            return 0.0
        return self.top_candidates[0].score / total


# ---------------------------------------------------------------------------
# Per-axis heuristic pipeline
# ---------------------------------------------------------------------------

class AxisHeuristicPipeline:
    """Full heuristic pipeline for a single classification axis.

    Processing order
    ----------------
    1. Normalize subject and body independently.
    2. Run Aho-Corasick matching on subject (×3 weight) and body (×1).
    3. Apply synonym bonus (+2) on matching synonyms.
    4. Accumulate cumulative scores (each repetition counts).
    5. Optionally extract serial numbers via regex.
    6. Return top-N :class:`CandidateMatch` and ambiguity flag.
    """

    def __init__(self, config: AxisKeywordConfig) -> None:
        self.config = config
        self._normalizer = TextNormalizer()
        self._matcher = AhoCorasickMatcher(config.keyword_map, config.synonym_map)
        self._serial_extractor = (
            SerialNumberExtractor(config.regex_patterns)
            if config.regex_patterns
            else None
        )

    def run(self, subject: str, body: str) -> AxisHeuristicResult:
        """Run heuristic pipeline on a single email.

        Args:
            subject: Email subject line (raw).
            body:    Email body (raw).

        Returns:
            :class:`AxisHeuristicResult` with ranked candidates and metadata.
        """
        norm_subject = self._normalizer.normalize(subject)
        norm_body = self._normalizer.normalize(body)

        scores: Dict[str, float] = {}
        hits: Dict[str, List[str]] = {}

        # --- Subject matches (weight = SCORE_SUBJECT_MATCH + optional synonym bonus)
        for kw, tag, is_syn in self._matcher.find_matches(norm_subject):
            increment = SCORE_SUBJECT_MATCH + (SCORE_SYNONYM_BONUS if is_syn else 0)
            scores[tag] = scores.get(tag, 0.0) + increment
            hits.setdefault(tag, []).append(f"subj:{kw}")

        # --- Body matches (weight = SCORE_BODY_MATCH + optional synonym bonus)
        for kw, tag, is_syn in self._matcher.find_matches(norm_body):
            increment = SCORE_BODY_MATCH + (SCORE_SYNONYM_BONUS if is_syn else 0)
            scores[tag] = scores.get(tag, 0.0) + increment
            hits.setdefault(tag, []).append(f"body:{kw}")

        # --- Serial / part number extraction (EQ_ axis only)
        serials: List[str] = []
        if self._serial_extractor:
            serials = self._serial_extractor.extract(f"{subject}\n{body}")

        # --- Filter by min score, sort descending, take top-N
        qualified = [
            (tag, score)
            for tag, score in scores.items()
            if score > self.config.min_score_threshold
        ]
        qualified.sort(key=lambda x: x[1], reverse=True)
        top_n = qualified[: self.config.max_candidates]

        candidates = [
            CandidateMatch(tag=t, score=s, hits=hits.get(t, []))
            for t, s in top_n
        ]

        return AxisHeuristicResult(
            axis_name=self.config.axis_name,
            prefix=self.config.prefix,
            top_candidates=candidates,
            is_ambiguous=self._is_ambiguous(top_n),
            serial_numbers=serials,
            debug={
                'raw_hits': {t: hits.get(t, []) for t, _ in qualified},
                'scores': dict(qualified),
            },
        )

    def _is_ambiguous(self, sorted_candidates: List[Tuple[str, float]]) -> bool:
        """Return ``True`` when the result needs LLM arbitration.

        A result is ambiguous when:
        - No candidates were found, **or**
        - The score gap between rank-1 and rank-2 is below
          ``config.ambiguity_threshold`` (as a fraction of the top score).
        """
        if not sorted_candidates:
            return True
        if len(sorted_candidates) == 1:
            return False
        top_score = sorted_candidates[0][1]
        second_score = sorted_candidates[1][1]
        if top_score == 0:
            return True
        gap_ratio = (top_score - second_score) / top_score
        return gap_ratio < self.config.ambiguity_threshold
