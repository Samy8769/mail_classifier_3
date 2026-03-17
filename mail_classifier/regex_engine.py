"""
Regex pattern matching engine for structured data.
Handles serial numbers, equipment IDs, anomaly references, etc.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from . import text_normalizer
from .logger import get_logger

logger = get_logger('regex_engine')


@dataclass
class RegexHit:
    """A regex match result."""
    pattern_name: str      # Name of the pattern that matched
    tag_name: str          # Resolved tag name
    matched_text: str      # The actual matched text
    weight: float          # Weight of this pattern
    group_dict: dict       # Named capture groups


class RegexEngine:
    """
    Compiles and applies regex patterns per axis.
    Patterns are loaded from axis configuration.
    """

    def __init__(self):
        # axis_name -> list of compiled pattern dicts
        self._patterns: Dict[str, List[dict]] = {}

    def register_patterns(self, axis_name: str,
                          pattern_defs: List[Dict]) -> None:
        """
        Register regex patterns for an axis.

        Each pattern_def contains:
            - name: str
            - pattern: str (regex)
            - tag_name: str (static) OR tag_template: str (e.g. "EQ_{0}")
            - weight: float
            - flags: Optional str ("IGNORECASE")
        """
        compiled = []
        for pdef in pattern_defs:
            flags = re.IGNORECASE if pdef.get("flags", "").upper() == "IGNORECASE" else 0
            try:
                compiled.append({
                    "name": pdef["name"],
                    "pattern": re.compile(pdef["pattern"], flags),
                    "tag_name": pdef.get("tag_name"),
                    "tag_template": pdef.get("tag_template"),
                    "weight": pdef.get("weight", 1.5),
                })
            except re.error as e:
                logger.error(f"Invalid regex for '{pdef['name']}': {e}")

        self._patterns[axis_name] = compiled
        logger.info(f"Registered {len(compiled)} regex patterns for '{axis_name}'")

    def search(self, axis_name: str, text: str,
               valid_tags: Optional[Set[str]] = None) -> List[RegexHit]:
        """
        Apply all registered patterns for an axis against text.

        Args:
            axis_name: Which axis patterns to use.
            text: Raw text (lightly normalized).
            valid_tags: Optional closed-list filter.

        Returns:
            List of RegexHit.
        """
        patterns = self._patterns.get(axis_name, [])
        if not patterns:
            return []

        normalized = text_normalizer.normalize_for_regex(text)
        hits = []

        for pdef in patterns:
            for match in pdef["pattern"].finditer(normalized):
                group_dict = match.groupdict()
                groups = match.groups()

                # Resolve tag name
                tag_name = pdef["tag_name"]
                if pdef.get("tag_template") and groups:
                    try:
                        tag_name = pdef["tag_template"].format(*groups, **group_dict)
                    except (KeyError, IndexError):
                        continue

                if not tag_name:
                    continue

                # Validate against closed list
                if valid_tags and tag_name not in valid_tags:
                    logger.debug(
                        f"Regex matched '{match.group()}' -> '{tag_name}' "
                        f"but not in valid tags, skipping"
                    )
                    continue

                hits.append(RegexHit(
                    pattern_name=pdef["name"],
                    tag_name=tag_name,
                    matched_text=match.group(),
                    weight=pdef["weight"],
                    group_dict=group_dict,
                ))

        return hits

    def has_patterns(self, axis_name: str) -> bool:
        return bool(self._patterns.get(axis_name))
