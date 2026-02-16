"""
Utility functions for mail_classifier package.
Provides centralized helpers for common operations.
"""

import re
from typing import List

# All known tag prefixes (sorted longest first for matching)
KNOWN_PREFIXES = ('NRB_', 'EQT_', 'EQ_', 'AN_', 'TC_', 'PC_', 'T_', 'S_', 'P_', 'A_', 'C_', 'F_', 'E_', 'Q_', 'J_')


def has_valid_prefix(tag: str) -> bool:
    """Check if a tag starts with a known prefix."""
    return any(tag.startswith(p) for p in KNOWN_PREFIXES)


def has_double_prefix(tag: str) -> bool:
    """
    Detect tags with double/compound prefixes like E_TC_DFC.
    Returns True if the remainder after the first prefix starts with another known prefix.
    """
    for prefix in KNOWN_PREFIXES:
        if tag.startswith(prefix):
            remainder = tag[len(prefix):]
            for inner_prefix in KNOWN_PREFIXES:
                if remainder.startswith(inner_prefix):
                    return True
            return False
    return False


def parse_categories(category_string: str) -> List[str]:
    """
    Parse comma-separated categories into a list.
    Consolidates duplicate logic from multiple modules.
    Filters out tags without known prefixes and tags with double prefixes.

    Args:
        category_string: Comma-separated category string

    Returns:
        List of stripped, non-empty, valid category strings
    """
    if not category_string:
        return []

    if isinstance(category_string, list):
        return category_string

    result = []
    for c in category_string.split(','):
        c = c.strip()
        if not c:
            continue

        # Must start with a known prefix
        if not has_valid_prefix(c):
            continue

        # Reject double/compound prefixes (e.g., E_TC_DFC)
        if has_double_prefix(c):
            continue

        # Reject tags with invalid characters or structure
        if not re.match(r'^[A-Z]+_[A-Za-z0-9_²\- ]+$', c):
            continue

        result.append(c)

    return result


def merge_category_sets(existing: str, new_categories: List[str],
                        remove: List[str] = None) -> str:
    """
    Merge existing and new categories, optionally removing some.

    Args:
        existing: Comma-separated existing categories
        new_categories: List of new categories to add
        remove: List of categories to remove

    Returns:
        Comma-separated merged categories
    """
    existing_set = set(parse_categories(existing))

    # Remove specified categories
    if remove:
        for cat in remove:
            existing_set.discard(cat)

    # Add new categories
    existing_set.update(new_categories)

    return ','.join(sorted(existing_set))
