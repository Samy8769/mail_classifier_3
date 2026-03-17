"""
Classification pipeline orchestrator.
Initializes all engines and AxisClassifiers from config.
"""

import os
import yaml
from typing import Dict, Optional, Set
from .keyword_engine import KeywordEngine
from .regex_engine import RegexEngine
from .scorer import HeuristicScorer
from .axis_classifier import AxisClassifier, AxisResult
from .logger import get_logger

logger = get_logger('pipeline')


def build_llm_prompt(axis_name, candidates, text, context, valid_tags):
    """
    Build a constrained LLM prompt for arbitration.
    The LLM receives candidates and valid tags — never free-classifies.
    """
    candidates_str = "\n".join(
        f"  - {c.tag_name} (score={c.confidence:.2f}, sources={c.sources})"
        for c in candidates[:10]
    )
    valid_tags_str = ", ".join(sorted(valid_tags)[:50])
    context_str = "\n".join(f"  {k}: {v}" for k, v in context.items())

    system_prompt = (
        f"Tu es un classificateur d'emails pour l'axe '{axis_name}'.\n"
        f"Tu dois choisir parmi les tags autorises ci-dessous.\n\n"
        f"## Tags autorises (liste fermee):\n{valid_tags_str}\n\n"
        f"## Candidats detectes automatiquement:\n{candidates_str}\n\n"
        f"## Contexte des autres axes:\n{context_str if context_str else 'Aucun'}\n\n"
        f"## Instructions:\n"
        f"- Choisis UNIQUEMENT parmi les tags autorises\n"
        f"- Reponds UNIQUEMENT avec les tags separes par des virgules\n"
        f"- Pas d'explication, pas de markdown\n"
    )
    return system_prompt, text


class ClassificationPipeline:
    """
    Central orchestrator for the local-first classification pipeline.
    Builds all engines at init, provides classify_axis() method.
    """

    def __init__(self, pipeline_config_path: str = None,
                 db=None, api_client=None):
        """
        Args:
            pipeline_config_path: Path to pipeline YAML config.
            db: DatabaseManager instance.
            api_client: Optional ParadigmAPIClient for LLM fallback.
        """
        self.db = db
        self.api_client = api_client
        self.axes_config: Dict[str, dict] = {}

        # Load config
        if pipeline_config_path and os.path.exists(pipeline_config_path):
            self._load_yaml(pipeline_config_path)

        # Build shared engines
        self.keyword_engine = KeywordEngine()
        self.regex_engine = RegexEngine()
        scoring_configs = {}

        for axis_name, axis_cfg in self.axes_config.items():
            kw_map = axis_cfg.get("keywords", {})
            if kw_map:
                self.keyword_engine.build_automaton(axis_name, kw_map)

            rx_patterns = axis_cfg.get("regex_patterns", [])
            if rx_patterns:
                self.regex_engine.register_patterns(axis_name, rx_patterns)

            scoring_configs[axis_name] = axis_cfg.get("scoring", {})

        self.scorer = HeuristicScorer(scoring_configs)

        # Cache valid tags per axis from DB
        self._valid_tags_by_axis: Dict[str, Set[str]] = {}
        if db:
            self._load_valid_tags()

        logger.info(f"Pipeline initialized: {len(self.axes_config)} axes configured")

    def _load_yaml(self, path: str):
        """Load pipeline config from YAML file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        for axis_def in data.get("axes", []):
            self.axes_config[axis_def["name"]] = {
                "keywords": axis_def.get("keywords", {}),
                "regex_patterns": axis_def.get("regex_patterns", []),
                "scoring": axis_def.get("scoring", {}),
                "max_tags": axis_def.get("max_tags"),
            }

    def _load_valid_tags(self):
        """Load valid tags per axis from database."""
        try:
            all_tags = self.db.get_all_active_tags_with_axis()
            for tag_info in all_tags:
                axis = tag_info['axis_name']
                self._valid_tags_by_axis.setdefault(axis, set()).add(
                    tag_info['tag_name']
                )
        except Exception as e:
            logger.warning(f"Could not load valid tags from DB: {e}")

    def classify_axis(self, axis_name: str, text: str,
                      context: Optional[Dict[str, str]] = None) -> Optional[AxisResult]:
        """
        Classify text on a single axis using the local-first pipeline.

        Returns:
            AxisResult or None if axis not configured.
        """
        if axis_name not in self.axes_config:
            return None

        axis_cfg = self.axes_config[axis_name]
        valid_tags = self._valid_tags_by_axis.get(axis_name, set())

        classifier = AxisClassifier(
            axis_name=axis_name,
            keyword_engine=self.keyword_engine,
            regex_engine=self.regex_engine,
            scorer=self.scorer,
            api_client=self.api_client,
            valid_tags=valid_tags,
            max_tags=axis_cfg.get("max_tags"),
            llm_prompt_builder=build_llm_prompt,
        )

        return classifier.classify(text, context)
