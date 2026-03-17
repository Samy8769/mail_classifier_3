"""
Heuristic scoring engine for candidate ranking.
Aggregates Aho-Corasick and regex hits into scored candidates per axis.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from .keyword_engine import KeywordHit
from .regex_engine import RegexHit
from .logger import get_logger

logger = get_logger('scorer')


@dataclass
class ScoredCandidate:
    """A scored tag candidate for a given axis."""
    tag_name: str
    raw_score: float
    keyword_hits: int
    regex_hits: int
    confidence: float = 0.0       # Normalized 0.0-1.0
    sources: List[str] = field(default_factory=list)


@dataclass
class ScoringResult:
    """Complete scoring result for one axis."""
    axis_name: str
    candidates: List[ScoredCandidate]   # Sorted by confidence desc
    needs_llm: bool
    llm_reason: Optional[str] = None


class HeuristicScorer:
    """
    Aggregates keyword and regex hits, applies weights,
    and determines whether LLM arbitration is needed.
    """

    def __init__(self, axis_configs: Dict[str, dict]):
        """
        Args:
            axis_configs: axis_name -> scoring config dict with keys:
                keyword_weight_multiplier (default 1.0)
                regex_weight_multiplier (default 1.5)
                confidence_threshold (default 0.7)
                ambiguity_margin (default 0.15)
                min_hits_for_confidence (default 1)
        """
        self._configs = axis_configs

    def score(self, axis_name: str,
              keyword_hits: List[KeywordHit],
              regex_hits: List[RegexHit]) -> ScoringResult:
        """Score and rank candidates for one axis."""
        config = self._configs.get(axis_name, {})
        kw_mult = config.get("keyword_weight_multiplier", 1.0)
        rx_mult = config.get("regex_weight_multiplier", 1.5)
        threshold = config.get("confidence_threshold", 0.7)
        margin = config.get("ambiguity_margin", 0.15)
        min_hits = config.get("min_hits_for_confidence", 1)

        # Aggregate scores per tag
        tag_scores: Dict[str, dict] = {}

        for hit in keyword_hits:
            entry = tag_scores.setdefault(hit.tag_name, {
                "raw": 0.0, "kw": 0, "rx": 0, "sources": []
            })
            entry["raw"] += hit.weight * kw_mult
            entry["kw"] += 1
            entry["sources"].append(f"kw:{hit.keyword}")

        for hit in regex_hits:
            entry = tag_scores.setdefault(hit.tag_name, {
                "raw": 0.0, "kw": 0, "rx": 0, "sources": []
            })
            entry["raw"] += hit.weight * rx_mult
            entry["rx"] += 1
            entry["sources"].append(f"rx:{hit.pattern_name}={hit.matched_text}")

        if not tag_scores:
            return ScoringResult(
                axis_name=axis_name, candidates=[],
                needs_llm=True, llm_reason="no_candidates",
            )

        # Normalize to confidence 0-1
        max_score = max(e["raw"] for e in tag_scores.values())
        candidates = []
        for tag_name, entry in tag_scores.items():
            confidence = (entry["raw"] / max_score) if max_score > 0 else 0.0
            total_hits = entry["kw"] + entry["rx"]
            if total_hits < min_hits:
                confidence *= 0.5

            candidates.append(ScoredCandidate(
                tag_name=tag_name,
                raw_score=entry["raw"],
                keyword_hits=entry["kw"],
                regex_hits=entry["rx"],
                confidence=round(confidence, 4),
                sources=entry["sources"],
            ))

        candidates.sort(key=lambda c: c.confidence, reverse=True)

        needs_llm, llm_reason = self._decide_llm_needed(
            candidates, threshold, margin
        )
        return ScoringResult(
            axis_name=axis_name, candidates=candidates,
            needs_llm=needs_llm, llm_reason=llm_reason,
        )

    def _decide_llm_needed(self, candidates: List[ScoredCandidate],
                           threshold: float,
                           margin: float) -> Tuple[bool, Optional[str]]:
        """
        Decide whether LLM arbitration is needed.

        Rules:
        1. No candidates -> LLM needed.
        2. Top candidate below threshold -> LLM needed.
        3. Top two within margin -> ambiguous, LLM needed.
        """
        if not candidates:
            return True, "no_candidates"

        top = candidates[0]
        if top.confidence < threshold:
            return True, f"low_confidence ({top.confidence:.2f} < {threshold})"

        if len(candidates) >= 2:
            gap = top.confidence - candidates[1].confidence
            if gap < margin:
                return True, (
                    f"ambiguous (gap={gap:.2f} < {margin}, "
                    f"#1={top.tag_name}:{top.confidence:.2f}, "
                    f"#2={candidates[1].tag_name}:{candidates[1].confidence:.2f})"
                )

        return False, None
