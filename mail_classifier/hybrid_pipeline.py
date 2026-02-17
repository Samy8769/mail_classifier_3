"""
Hybrid multi-axis classification pipeline.

Combines fast heuristic matching (Aho-Corasick + regex) with selective
LLM arbitration:

  For each axis
  ─────────────
  1. Run :class:`AxisHeuristicPipeline` → scored candidates.
  2. If a clear winner exists (score gap ≥ threshold, confidence ≥ cutoff)
     → accept directly, **no LLM call**.
  3. If ambiguous or no match → call LLM with the *candidate list only*.
     The LLM cannot invent tags; it picks from heuristic candidates.
  4. Emit :class:`AxisClassificationResult` with value + confidence + method.

The pipeline produces:
  • a flat ``List[str]`` of category tags (compatible with existing code),
  • a structured :class:`HybridClassificationOutput` including a JSON
    context block for downstream LLM usage.

JSON context format (``HybridClassificationOutput.to_llm_context()``)
─────────────────────────────────────────────────────────────────────
{
  "axes": {
    "type_mail":  {"value": "T_Commande",  "confidence": 0.82, "method": "heuristic"},
    "projet":     {"value": "P_GALILEO",   "confidence": 0.74, "method": "llm"},
    ...
  },
  "serial_numbers": ["CAM-001234", "SN:99999"],
  "debug": {
    "raw_hits": {"type_mail": {"T_Commande": ["subj:commande", "body:bdc"]}, ...},
    "scores":   {"type_mail": {"T_Commande": 6.0, "T_Offre": 1.0}, ...}
  }
}
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .axis_keywords import AXIS_CONFIGS
from .heuristic_engine import (
    AxisHeuristicPipeline,
    AxisHeuristicResult,
    AxisKeywordConfig,
    CandidateMatch,
)
from .logger import get_logger

logger = get_logger('hybrid_pipeline')


# ---------------------------------------------------------------------------
# LLM arbitration prompt
# ---------------------------------------------------------------------------

_LLM_ARBITRATION_PROMPT = """\
Tu es un classifieur d'emails de l'industrie spatiale.

Axe : {axis_name}  (préfixe {prefix})

Candidats heuristiques (ordre par score décroissant) :
{candidates_str}

Contexte de l'email :
{email_context}

Axes déjà classifiés :
{other_axes}

Règle absolue :
  • Choisis UNE SEULE valeur parmi les candidats listés ci-dessus.
  • Si aucun candidat ne convient, réponds exactement : AUCUN
  • N'invente jamais de tag hors liste.

Réponds uniquement avec le tag choisi (ex : T_Commande) ou AUCUN.\
"""


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class AxisClassificationResult:
    """Classification outcome for a single axis.

    Attributes:
        axis_name:   Axis identifier (e.g. ``'type_mail'``).
        prefix:      Tag prefix (e.g. ``'T_'``).
        value:       Final tag (e.g. ``'T_Commande'``), or ``None``.
        confidence:  Score in [0, 1].
        method:      ``'heuristic'``, ``'llm'``, or ``'none'``.
        candidates:  Heuristic candidates (for debug / audit trail).
        debug:       Detailed scoring info from the heuristic engine.
    """

    axis_name: str
    prefix: str
    value: Optional[str]
    confidence: float
    method: str                      # 'heuristic' | 'llm' | 'none'
    candidates: List[Dict[str, Any]]
    debug: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HybridClassificationOutput:
    """Full output of :class:`HybridClassificationPipeline` for one email.

    Attributes:
        axes:           Per-axis results.
        serial_numbers: All serial / part numbers found across axes.
        categories:     Flat list of final tags (compatible with legacy code).
    """

    axes: Dict[str, AxisClassificationResult]
    serial_numbers: List[str]
    categories: List[str]

    def to_llm_context(self) -> Dict[str, Any]:
        """Build the structured JSON context dictionary.

        Suitable for passing as additional context to any downstream LLM
        call (e.g. the existing summary or validation prompts).

        Returns:
            Dictionary with keys ``axes``, ``serial_numbers``, ``debug``.
        """
        axes_summary: Dict[str, Any] = {}
        raw_hits: Dict[str, Any] = {}
        scores: Dict[str, Any] = {}

        for name, result in self.axes.items():
            axes_summary[name] = {
                'value': result.value,
                'confidence': round(result.confidence, 3),
                'method': result.method,
            }
            raw_hits[name] = result.debug.get('raw_hits', {})
            scores[name] = result.debug.get('scores', {})

        return {
            'axes': axes_summary,
            'serial_numbers': self.serial_numbers,
            'debug': {
                'raw_hits': raw_hits,
                'scores': scores,
            },
        }

    def to_llm_context_json(self, indent: int = 2) -> str:
        """Serialize :meth:`to_llm_context` as a JSON string."""
        return json.dumps(self.to_llm_context(), ensure_ascii=False, indent=indent)


# ---------------------------------------------------------------------------
# Per-axis hybrid classifier
# ---------------------------------------------------------------------------

class HybridAxisClassifier:
    """Classify one axis using heuristic first, LLM only when necessary.

    Decision tree
    ─────────────
    1. No candidates at all
       → LLM (if available, with empty candidate hint)  else  → ``None``
    2. Clear winner (not ambiguous AND confidence ≥ ``CONFIDENCE_CUTOFF``)
       → accept heuristic result directly.
    3. Ambiguous
       → LLM picks from the top-N heuristic candidates.
    4. LLM unavailable / disabled
       → use best heuristic candidate with reduced confidence.

    The LLM is **never** allowed to invent a tag outside the candidate list.
    """

    CONFIDENCE_CUTOFF = 0.55  # minimum normalised confidence for "clear winner"

    def __init__(self, api_client=None, use_llm_for_ambiguous: bool = True) -> None:
        """
        Args:
            api_client:             :class:`ParadigmAPIClient` or compatible.
                                    Pass ``None`` to disable LLM completely.
            use_llm_for_ambiguous:  If ``False``, never trigger LLM calls.
        """
        self.api = api_client
        self.use_llm = use_llm_for_ambiguous and api_client is not None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def classify(
        self,
        heuristic_result: AxisHeuristicResult,
        axis_config: AxisKeywordConfig,
        email_context: str = '',
        other_axes_context: Optional[Dict[str, Optional[str]]] = None,
    ) -> AxisClassificationResult:
        """Return classification result for one axis.

        Args:
            heuristic_result:   Output of :class:`AxisHeuristicPipeline.run`.
            axis_config:        Axis keyword config (used for metadata).
            email_context:      Email summary / excerpt for LLM context.
            other_axes_context: ``{axis_name: tag_value}`` from already
                                processed axes (dependency context).

        Returns:
            :class:`AxisClassificationResult`.
        """
        candidates_summary = [
            {'tag': c.tag, 'score': c.score, 'hits': c.hits}
            for c in heuristic_result.top_candidates
        ]
        other = other_axes_context or {}

        # --- 1. No heuristic candidates ---
        if not heuristic_result.top_candidates:
            if self.use_llm and email_context:
                return self._llm_decision(
                    heuristic_result, candidates_summary, email_context, other, 'no_match'
                )
            return self._make_result(heuristic_result, None, 0.0, 'none', candidates_summary)

        best = heuristic_result.best
        confidence = heuristic_result.best_confidence

        # --- 2. Clear winner ---
        if not heuristic_result.is_ambiguous and confidence >= self.CONFIDENCE_CUTOFF:
            return self._make_result(
                heuristic_result, best.tag, confidence, 'heuristic', candidates_summary
            )

        # --- 3. Ambiguous → LLM ---
        if self.use_llm and email_context:
            return self._llm_decision(
                heuristic_result, candidates_summary, email_context, other, 'ambiguous'
            )

        # --- 4. Fallback: best heuristic with reduced confidence ---
        return self._make_result(
            heuristic_result,
            best.tag,
            confidence * 0.5,
            'heuristic',
            candidates_summary,
            extra_debug={'note': 'ambiguous_no_llm'},
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _make_result(
        self,
        hr: AxisHeuristicResult,
        value: Optional[str],
        confidence: float,
        method: str,
        candidates: List[Dict],
        extra_debug: Optional[Dict] = None,
    ) -> AxisClassificationResult:
        debug = dict(hr.debug)
        if extra_debug:
            debug.update(extra_debug)
        return AxisClassificationResult(
            axis_name=hr.axis_name,
            prefix=hr.prefix,
            value=value,
            confidence=confidence,
            method=method,
            candidates=candidates,
            debug=debug,
        )

    def _llm_decision(
        self,
        hr: AxisHeuristicResult,
        candidates_summary: List[Dict],
        email_context: str,
        other_axes: Dict[str, Optional[str]],
        reason: str,
    ) -> AxisClassificationResult:
        """Call LLM to resolve ambiguity; result must be from candidate list."""
        valid_tags = {c.tag for c in hr.top_candidates}

        candidates_str = (
            '\n'.join(
                f"  - {c.tag}  (score={c.score:.1f})"
                for c in hr.top_candidates
            )
            or '  (aucun candidat heuristique)'
        )
        other_axes_str = (
            '\n'.join(f"  {k}: {v}" for k, v in other_axes.items() if v)
            or '  (aucun)'
        )

        prompt = _LLM_ARBITRATION_PROMPT.format(
            axis_name=hr.axis_name,
            prefix=hr.prefix,
            candidates_str=candidates_str,
            email_context=email_context[:2000],
            other_axes=other_axes_str,
        )

        try:
            raw_response = self.api.call_paradigm(prompt, '').strip()
        except Exception as exc:
            logger.error(f"LLM call failed for axis '{hr.axis_name}': {exc}")
            best = hr.best
            return self._make_result(
                hr,
                best.tag if best else None,
                best.score / max(sum(c.score for c in hr.top_candidates), 1) * 0.5 if best else 0.0,
                'heuristic',
                candidates_summary,
                extra_debug={'llm_error': str(exc)},
            )

        chosen = self._parse_llm_response(raw_response, valid_tags, hr)
        confidence = 0.9 if chosen else 0.85

        return AxisClassificationResult(
            axis_name=hr.axis_name,
            prefix=hr.prefix,
            value=chosen,
            confidence=confidence,
            method='llm',
            candidates=candidates_summary,
            debug={
                **hr.debug,
                'llm_reason': reason,
                'llm_response': raw_response,
            },
        )

    @staticmethod
    def _parse_llm_response(
        response: str,
        valid_tags: set,
        hr: AxisHeuristicResult,
    ) -> Optional[str]:
        """Extract a valid tag from the LLM response string.

        Strategy (in order):
        1. Exact match in valid_tags.
        2. Valid tag is a substring of response.
        3. Response is a substring of a valid tag (handles typos).
        4. Fall back to heuristic best if available.
        """
        if not response or response.upper() == 'AUCUN':
            return None

        # Exact
        if response in valid_tags:
            return response

        # Tag contained in response
        for tag in valid_tags:
            if tag in response:
                return tag

        # Response contained in a tag (partial match)
        upper_resp = response.upper()
        for tag in valid_tags:
            if upper_resp in tag.upper():
                return tag

        # LLM returned something unexpected
        logger.warning(
            f"LLM returned unexpected response '{response}' "
            f"for axis '{hr.axis_name}'; falling back to heuristic best."
        )
        return hr.best.tag if hr.top_candidates else None


# ---------------------------------------------------------------------------
# Full multi-axis pipeline
# ---------------------------------------------------------------------------

class HybridClassificationPipeline:
    """Multi-axis hybrid classification pipeline.

    For each axis (in ``axis_order``):
      1. :class:`AxisHeuristicPipeline` → scored candidates + serial numbers.
      2. :class:`HybridAxisClassifier` → final tag + confidence + method.
      3. Pass resolved context to downstream axes (respects dependencies).

    Usage
    ─────
    ::

        pipeline = HybridClassificationPipeline(api_client=my_api)
        output = pipeline.classify_email(subject="...", body="...")
        print(output.categories)
        print(output.to_llm_context_json())

    Attributes:
        confidence_threshold: Minimum confidence for a tag to appear in
                              ``output.categories``.  Default 0.0 (all tags).
    """

    #: Default processing order (mirrors settings.json dependencies)
    DEFAULT_AXIS_ORDER: List[str] = [
        'type_mail',
        'statut',
        'client',
        'affaire',
        'projet',
        'fournisseur',
        'equipement_type',
        'equipement_designation',
        'essais',
        'technique',
        'qualite',
        'jalons',
        'anomalies',
        'nrb',
    ]

    def __init__(
        self,
        api_client=None,
        axis_configs: Optional[Dict[str, AxisKeywordConfig]] = None,
        use_llm_for_ambiguous: bool = True,
        confidence_threshold: float = 0.0,
    ) -> None:
        """
        Args:
            api_client:             LLM API client (optional).
            axis_configs:           Override default ``AXIS_CONFIGS`` dict
                                    (useful for tests / custom axes).
            use_llm_for_ambiguous:  Trigger LLM for ambiguous axes.
            confidence_threshold:   Minimum confidence to include a tag in
                                    the ``categories`` output list.
        """
        self.api = api_client
        self.axis_configs: Dict[str, AxisKeywordConfig] = axis_configs or AXIS_CONFIGS
        self.confidence_threshold = confidence_threshold

        # Build one heuristic pipeline per axis
        self._heuristic_pipelines: Dict[str, AxisHeuristicPipeline] = {
            name: AxisHeuristicPipeline(cfg)
            for name, cfg in self.axis_configs.items()
        }

        self._axis_classifier = HybridAxisClassifier(
            api_client=api_client,
            use_llm_for_ambiguous=use_llm_for_ambiguous,
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def classify_email(
        self,
        subject: str,
        body: str,
        email_summary: str = '',
        axis_order: Optional[List[str]] = None,
    ) -> HybridClassificationOutput:
        """Classify one email across all configured axes.

        Args:
            subject:       Email subject (raw).
            body:          Email body (raw).
            email_summary: Optional LLM summary for LLM arbitration context.
                           Falls back to ``Subject + first 1000 chars of body``.
            axis_order:    Override processing order.

        Returns:
            :class:`HybridClassificationOutput`.
        """
        order = axis_order or self.DEFAULT_AXIS_ORDER
        email_context = email_summary or f"Sujet: {subject}\n\nCorps: {body[:1000]}"

        results: Dict[str, AxisClassificationResult] = {}
        all_serials: List[str] = []
        other_axes_context: Dict[str, Optional[str]] = {}

        for axis_name in order:
            hp = self._heuristic_pipelines.get(axis_name)
            if hp is None:
                logger.debug(f"No heuristic config for axis '{axis_name}' – skipped.")
                continue

            # --- Heuristic ---
            hr = hp.run(subject=subject, body=body)
            all_serials.extend(hr.serial_numbers)

            # --- Hybrid decision ---
            axis_result = self._axis_classifier.classify(
                heuristic_result=hr,
                axis_config=self.axis_configs[axis_name],
                email_context=email_context,
                other_axes_context=other_axes_context,
            )
            results[axis_name] = axis_result

            # Pass to downstream axes
            other_axes_context[axis_name] = axis_result.value

            logger.debug(
                "axis=%-25s  value=%-25s  conf=%.2f  method=%s",
                axis_name,
                str(axis_result.value),
                axis_result.confidence,
                axis_result.method,
            )

        categories = [
            r.value
            for r in results.values()
            if r.value and r.confidence >= self.confidence_threshold
        ]

        return HybridClassificationOutput(
            axes=results,
            serial_numbers=sorted(set(all_serials)),
            categories=categories,
        )

    def classify_emails(
        self,
        emails: List[Dict[str, Any]],
        email_summary: str = '',
        axis_order: Optional[List[str]] = None,
    ) -> HybridClassificationOutput:
        """Classify a list of emails (e.g. a conversation thread).

        All emails are concatenated into a single subject+body before
        running the pipeline, giving a conversation-level view.

        Args:
            emails:        List of ``{'subject': str, 'body': str, ...}`` dicts.
            email_summary: Optional pre-computed conversation summary.
            axis_order:    Override axis processing order.

        Returns:
            :class:`HybridClassificationOutput` for the conversation.
        """
        combined_subject = ' | '.join(
            e.get('subject', '') for e in emails if e.get('subject')
        )
        combined_body = '\n\n---\n\n'.join(
            e.get('body', '') for e in emails if e.get('body')
        )
        return self.classify_email(
            subject=combined_subject,
            body=combined_body,
            email_summary=email_summary,
            axis_order=axis_order,
        )
