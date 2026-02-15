"""
State management module for tracking processed conversations.
Implements caching to avoid reprocessing already-analyzed emails.
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from .logger import get_logger

logger = get_logger('state_manager')


class StateManager:
    """Manages conversation processing state with JSON cache and Outlook verification."""

    def __init__(self, state_config: Dict[str, Any], outlook_config: Dict[str, Any]):
        """
        Initialize state manager.

        Args:
            state_config: State configuration (enabled, cache_file, use_outlook_categories)
            outlook_config: Outlook configuration (done_marker_category)
        """
        self.enabled = state_config.get('enabled', True)
        self.cache_file = state_config.get('cache_file', '.classifier_cache.json')
        self.use_outlook_categories = state_config.get('use_outlook_categories', True)
        self.done_category = outlook_config['done_marker_category']
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict[str, Any]:
        """
        Load cache from JSON file if exists.

        Returns:
            Cache dictionary
        """
        if not self.enabled or not os.path.exists(self.cache_file):
            return {}

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load cache: {e}")
            return {}

    def _save_cache(self):
        """Persist cache to JSON file."""
        if not self.enabled:
            return

        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not save cache: {e}")

    def is_conversation_processed(self, conversation_id: str) -> bool:
        """
        Check if conversation has been processed (fast cache check).

        Args:
            conversation_id: Conversation ID to check

        Returns:
            True if conversation found in cache
        """
        return conversation_id in self.cache

    def verify_with_outlook(self, email_client, folder, conversation_id: str) -> bool:
        """
        Authoritative check via Outlook categories.
        Checks if any email in conversation has done_category.
        Optimized: Uses Outlook's Restrict filter instead of iterating all items.

        Args:
            email_client: EmailClient instance
            folder: Outlook folder object
            conversation_id: Conversation ID to verify

        Returns:
            True if conversation already processed in Outlook
        """
        if not self.use_outlook_categories:
            return False

        try:
            # Use Outlook's Restrict method for efficient filtering
            # This is much faster than iterating through all items
            filter_str = f"@SQL=\"urn:schemas:httpmail:conversationindex\" LIKE '{conversation_id[:40]}%'"
            try:
                filtered_items = folder.Items.Restrict(filter_str)
            except Exception:
                # Fallback to simple iteration if Restrict fails
                filtered_items = folder.Items

            for message in filtered_items:
                try:
                    if message.ConversationID == conversation_id:
                        if self.done_category in message.Categories:
                            # Update cache if not present
                            if conversation_id not in self.cache:
                                # Extract categories (excluding done marker)
                                cats = [c.strip() for c in message.Categories.split(',') if c.strip()]
                                cats = [c for c in cats if c != self.done_category]
                                self.cache_conversation(conversation_id, cats)
                            return True
                except Exception:
                    continue
            return False
        except Exception as e:
            logger.warning(f"Could not verify with Outlook: {e}")
            return False

    def cache_conversation(self, conversation_id: str, categories: List[str]):
        """
        Save processed conversation to cache.

        Args:
            conversation_id: Conversation ID
            categories: List of categories assigned
        """
        if not self.enabled:
            return

        self.cache[conversation_id] = {
            'categories': categories,
            'timestamp': datetime.now().isoformat(),
            'processed': True
        }
        self._save_cache()

    def get_cached_categories(self, conversation_id: str) -> Optional[List[str]]:
        """
        Retrieve cached categories for conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            List of categories or None if not found
        """
        if conversation_id in self.cache:
            return self.cache[conversation_id].get('categories', [])
        return None

    def clear_cache(self):
        """Clear all cached data."""
        self.cache = {}
        self._save_cache()
        logger.info("Cache cleared.")
