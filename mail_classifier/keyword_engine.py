"""
Aho-Corasick keyword matching engine (pure Python, no external dependency).
Builds one automaton per axis from keywords + synonyms.
"""

from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from . import text_normalizer
from .logger import get_logger

logger = get_logger('keyword_engine')


@dataclass
class KeywordHit:
    """A single keyword match result."""
    keyword: str       # The original keyword that matched
    tag_name: str      # The tag this keyword maps to (e.g. "P_YODA_CE")
    position: int      # End position in normalized text
    weight: float      # Weight from config


class _AhoNode:
    """Trie node for the Aho-Corasick automaton."""
    __slots__ = ('children', 'fail', 'outputs')

    def __init__(self):
        self.children: Dict[str, '_AhoNode'] = {}
        self.fail: Optional['_AhoNode'] = None
        self.outputs: List[Tuple[str, str, float]] = []  # (tag_name, original_kw, weight)


class _AhoAutomaton:
    """Pure-Python Aho-Corasick automaton."""

    def __init__(self):
        self.root = _AhoNode()
        self._built = False

    def add_word(self, word: str, tag_name: str, original_kw: str, weight: float):
        """Insert a normalized keyword into the trie."""
        node = self.root
        for ch in word:
            if ch not in node.children:
                node.children[ch] = _AhoNode()
            node = node.children[ch]
        node.outputs.append((tag_name, original_kw, weight))

    def build(self):
        """Build failure links (BFS) to complete the automaton."""
        queue = deque()
        # Initialize depth-1 nodes
        for ch, child in self.root.children.items():
            child.fail = self.root
            queue.append(child)

        # BFS to build failure links
        while queue:
            current = queue.popleft()
            for ch, child in current.children.items():
                queue.append(child)
                # Walk up failure links to find longest proper suffix
                fail = current.fail
                while fail and ch not in fail.children:
                    fail = fail.fail
                child.fail = fail.children[ch] if fail else self.root
                if child.fail is child:
                    child.fail = self.root
                # Merge outputs from fail node
                child.outputs = child.outputs + child.fail.outputs

        self._built = True

    def search(self, text: str) -> List[Tuple[int, str, str, float]]:
        """
        Search text and return all matches.

        Returns:
            List of (end_position, tag_name, original_kw, weight).
        """
        if not self._built:
            self.build()

        results = []
        node = self.root
        for i, ch in enumerate(text):
            while node and ch not in node.children:
                node = node.fail
            if node is None:
                node = self.root
                continue
            node = node.children[ch]
            for tag_name, original_kw, weight in node.outputs:
                results.append((i, tag_name, original_kw, weight))
        return results


class KeywordEngine:
    """
    Builds and queries Aho-Corasick automatons for fast multi-keyword matching.
    One automaton per axis, shared across all classifications.
    """

    def __init__(self):
        self._automatons: Dict[str, _AhoAutomaton] = {}

    def build_automaton(self, axis_name: str,
                        keyword_map: Dict[str, List[Dict]]) -> None:
        """
        Build an Aho-Corasick automaton for one axis.

        Args:
            axis_name: Classification axis name.
            keyword_map: tag_name -> list of {"keyword": str, "weight": float}.
        """
        automaton = _AhoAutomaton()
        kw_count = 0

        for tag_name, keywords in keyword_map.items():
            for kw_entry in keywords:
                raw_keyword = kw_entry["keyword"]
                weight = kw_entry.get("weight", 1.0)
                normalized_kw = text_normalizer.normalize(raw_keyword)
                if not normalized_kw:
                    continue
                automaton.add_word(normalized_kw, tag_name, raw_keyword, weight)
                kw_count += 1

        automaton.build()
        self._automatons[axis_name] = automaton
        logger.info(
            f"Built automaton for '{axis_name}': "
            f"{len(keyword_map)} tags, {kw_count} keywords"
        )

    def search(self, axis_name: str, text: str) -> List[KeywordHit]:
        """
        Search normalized text against the automaton for a given axis.

        Args:
            axis_name: Which axis automaton to use.
            text: Raw text (normalized internally).

        Returns:
            List of KeywordHit (may contain duplicates for same tag).
        """
        automaton = self._automatons.get(axis_name)
        if automaton is None:
            return []

        normalized_text = text_normalizer.normalize(text)
        hits = []
        for end_pos, tag_name, original_kw, weight in automaton.search(normalized_text):
            hits.append(KeywordHit(
                keyword=original_kw,
                tag_name=tag_name,
                position=end_pos,
                weight=weight,
            ))
        return hits

    def has_automaton(self, axis_name: str) -> bool:
        return axis_name in self._automatons
