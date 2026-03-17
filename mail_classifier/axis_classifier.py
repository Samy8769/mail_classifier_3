"""
Per-axis classification pipeline.
Orchestrates: keywords -> regex -> scoring -> optional LLM.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set
from .keyword_engine import KeywordEngine
from .regex_engine import RegexEngine
from .scorer import HeuristicScorer, ScoredCandidate, ScoringResult
from .logger import get_logger

logger = get_logger('axis_classifier')


@dataclass
class AxisResult:
    """Result of classifying one axis."""
    axis_name: str
    selected_tags: List[str]
    confidence: float
    method: str                                     # "local", "llm", "local+llm", etc.
    scoring_result: Optional[ScoringResult] = None
    llm_response: Optional[str] = None


class AxisClassifier:
    """
    Classifies one axis using the full pipeline:
    text -> Aho-Corasick -> regex -> scoring -> optional LLM.
    """

    def __init__(self,
                 axis_name: str,
                 keyword_engine: KeywordEngine,
                 regex_engine: RegexEngine,
                 scorer: HeuristicScorer,
                 api_client=None,
                 valid_tags: Optional[Set[str]] = None,
                 max_tags: Optional[int] = None,
                 llm_prompt_builder: Optional[Callable] = None):
        """
        Args:
            axis_name: Classification axis name.
            keyword_engine: Shared KeywordEngine.
            regex_engine: Shared RegexEngine.
            scorer: Shared HeuristicScorer.
            api_client: Optional API client for LLM fallback.
            valid_tags: Set of valid tag names for this axis (DB).
            max_tags: Max number of tags for this axis.
            llm_prompt_builder: Callable(axis_name, candidates, text, context, valid_tags)
                                -> (system_prompt, user_content).
        """
        self.axis_name = axis_name
        self.keyword_engine = keyword_engine
        self.regex_engine = regex_engine
        self.scorer = scorer
        self.api_client = api_client
        self.valid_tags = valid_tags or set()
        self.max_tags = max_tags
        self.llm_prompt_builder = llm_prompt_builder

    def classify(self, text: str,
                 context: Optional[Dict[str, str]] = None) -> AxisResult:
        """
        Run the full classification pipeline for this axis.

        Args:
            text: Combined email text (subject + body + metadata).
            context: Results from previously classified axes.

        Returns:
            AxisResult with selected tags and metadata.
        """
        # Stage 1: Aho-Corasick
        kw_hits = self.keyword_engine.search(self.axis_name, text)
        logger.debug(
            f"[{self.axis_name}] Aho-Corasick: {len(kw_hits)} hits "
            f"({len(set(h.tag_name for h in kw_hits))} unique tags)"
        )

        # Stage 2: Regex
        rx_hits = self.regex_engine.search(
            self.axis_name, text, valid_tags=self.valid_tags
        )
        logger.debug(f"[{self.axis_name}] Regex: {len(rx_hits)} hits")

        # Stage 3: Scoring
        scoring_result = self.scorer.score(self.axis_name, kw_hits, rx_hits)

        # Stage 4: Decision
        if not scoring_result.needs_llm:
            selected = self._select_top_tags(scoring_result.candidates)
            logger.info(
                f"[{self.axis_name}] LOCAL: {', '.join(selected)} "
                f"(confidence={scoring_result.candidates[0].confidence:.2f})"
            )
            return AxisResult(
                axis_name=self.axis_name,
                selected_tags=selected,
                confidence=scoring_result.candidates[0].confidence,
                method="local",
                scoring_result=scoring_result,
            )

        # Stage 5: LLM arbitration
        logger.info(f"[{self.axis_name}] LLM needed: {scoring_result.llm_reason}")
        return self._classify_with_llm(text, scoring_result, context or {})

    def _select_top_tags(self, candidates: List[ScoredCandidate]) -> List[str]:
        """Select top N tags respecting max_tags and valid_tags."""
        limit = self.max_tags or len(candidates)
        selected = []
        for c in candidates[:limit]:
            if not self.valid_tags or c.tag_name in self.valid_tags:
                selected.append(c.tag_name)
        return selected if selected else [candidates[0].tag_name]

    def _classify_with_llm(self, text: str,
                           scoring_result: ScoringResult,
                           context: Dict[str, str]) -> AxisResult:
        """
        LLM arbitration: constrained classification using candidates as hints.
        The LLM picks from candidates or valid tags, never free-classifies.
        """
        if not self.api_client or not self.llm_prompt_builder:
            # No LLM available: fall back to top local candidate
            if scoring_result.candidates:
                selected = self._select_top_tags(scoring_result.candidates)
                return AxisResult(
                    axis_name=self.axis_name,
                    selected_tags=selected,
                    confidence=scoring_result.candidates[0].confidence * 0.8,
                    method="local_fallback",
                    scoring_result=scoring_result,
                )
            return AxisResult(
                axis_name=self.axis_name,
                selected_tags=[],
                confidence=0.0,
                method="no_match",
                scoring_result=scoring_result,
            )

        # Build constrained prompt
        system_prompt, user_content = self.llm_prompt_builder(
            self.axis_name,
            scoring_result.candidates,
            text,
            context,
            self.valid_tags,
        )

        try:
            llm_response = self.api_client.call_paradigm(system_prompt, user_content)

            from .utils import parse_categories
            proposed = parse_categories(llm_response)
            selected = [t for t in proposed if t in self.valid_tags]

            if not selected and scoring_result.candidates:
                selected = self._select_top_tags(scoring_result.candidates)
                method = "local_fallback_after_llm"
            else:
                method = "llm" if not scoring_result.candidates else "local+llm"

            if self.max_tags and len(selected) > self.max_tags:
                selected = selected[:self.max_tags]

            confidence = (
                scoring_result.candidates[0].confidence
                if scoring_result.candidates else 0.5
            )

            return AxisResult(
                axis_name=self.axis_name,
                selected_tags=selected,
                confidence=confidence,
                method=method,
                scoring_result=scoring_result,
                llm_response=llm_response,
            )
        except Exception as e:
            logger.error(f"[{self.axis_name}] LLM call failed: {e}")
            if scoring_result.candidates:
                selected = self._select_top_tags(scoring_result.candidates)
                return AxisResult(
                    axis_name=self.axis_name,
                    selected_tags=selected,
                    confidence=scoring_result.candidates[0].confidence * 0.7,
                    method="local_fallback_on_error",
                    scoring_result=scoring_result,
                )
            return AxisResult(
                axis_name=self.axis_name,
                selected_tags=[],
                confidence=0.0,
                method="error",
                scoring_result=scoring_result,
            )
