"""
Utility functions for mail_classifier package.
Provides centralized helpers for common operations.
"""

from typing import List


def parse_categories(category_string: str) -> List[str]:
    """
    Parse comma-separated categories into a list.
    Consolidates duplicate logic from multiple modules.

    Args:
        category_string: Comma-separated category string

    Returns:
        List of stripped, non-empty category strings
    """
    if not category_string:
        return []

    if isinstance(category_string, list):
        return category_string

    return [c.strip() for c in category_string.split(',') if c.strip()]


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
