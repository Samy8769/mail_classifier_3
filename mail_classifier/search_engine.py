"""
Semantic search orchestration for email retrieval.
High-level interface for searching emails by meaning.
"""

from typing import List, Dict, Optional
from datetime import datetime
import json
from .logger import get_logger

logger = get_logger('search_engine')


class SearchEngine:
    """
    High-level semantic search interface.
    Orchestrates vector search, result ranking, and email retrieval.
    """

    def __init__(self, vector_store: 'VectorStore', db: 'DatabaseManager',
                 email_client: Optional['EmailClient'] = None):
        """
        Args:
            vector_store: VectorStore instance
            db: DatabaseManager instance
            email_client: Optional EmailClient for Outlook retrieval
        """
        self.vector_store = vector_store
        self.db = db
        self.email_client = email_client

    def search(self, query: str, top_k: int = 10,
               retrieve_full_emails: bool = True,
               filters: Optional[Dict] = None) -> List[Dict]:
        """
        Perform semantic search and retrieve emails.

        Args:
            query: Natural language search query
            top_k: Number of results to return
            retrieve_full_emails: If True, fetch complete email data
            filters: Optional filters (date_range, sender, tags, etc.)

        Returns:
            List of email results with metadata and relevance scores
        """
        logger.info(f"Searching for: '{query}'")
        logger.info("=" * 60)

        # Vector similarity search (returns top_k * 2 to allow for deduplication)
        chunk_results = self.vector_store.similarity_search(
            query,
            top_k=top_k * 2
        )

        if not chunk_results:
            logger.info("No matching chunks found")
            return []

        # Deduplicate by email_id and rank by best chunk score
        email_scores = {}
        chunk_map = {}

        for result in chunk_results:
            email_id = result['email_id']
            score = result['score']

            # Keep best score per email
            if email_id not in email_scores or email_scores[email_id] < score:
                email_scores[email_id] = score
                chunk_map[email_id] = result

        # Sort by score (descending)
        ranked_emails = sorted(email_scores.items(), key=lambda x: x[1], reverse=True)
        ranked_emails = ranked_emails[:top_k]

        logger.info(f"Found {len(chunk_results)} chunks -> {len(ranked_emails)} unique emails")

        # Apply filters if specified
        if filters:
            ranked_emails = self._apply_filters(ranked_emails, filters)
            logger.info(f"After filtering: {len(ranked_emails)} emails")

        # Retrieve full email data
        results = []
        for email_id, score in ranked_emails:
            email_data = self.db.get_email(email_id)
            if not email_data:
                continue

            # Get tags/classifications
            classifications = self.db.get_classifications_for_email(email_id)
            tags = [c['tag_name'] for c in classifications]

            # Get best matching chunk
            best_chunk = chunk_map.get(email_id, {})

            # Build result
            result = {
                'email_id': email_id,
                'relevance_score': score,
                'subject': email_data['subject'],
                'sender_name': email_data['sender_name'],
                'sender_email': email_data['sender_email'],
                'received_time': email_data['received_time'],
                'conversation_id': email_data['conversation_id'],
                'tags': tags,
                'matching_chunk': {
                    'chunk_id': best_chunk.get('chunk_id'),
                    'text_preview': best_chunk.get('chunk_text', '')[:300] + '...',
                    'token_count': best_chunk.get('token_count', 0)
                }
            }

            # Add full body if requested
            if retrieve_full_emails:
                result['body'] = email_data['body']
                result['body_preview'] = email_data['body'][:500] + '...' if len(email_data['body']) > 500 else email_data['body']
            else:
                result['body_preview'] = email_data['body'][:300] + '...'

            results.append(result)

        # Log search to database
        self._log_search(query, results, top_k)

        logger.info(f"Returning {len(results)} results")
        return results

    def _apply_filters(self, ranked_emails: List[tuple], filters: Dict) -> List[tuple]:
        """
        Apply filters to search results.

        Supported filters:
        - start_date: Filter emails after this date
        - end_date: Filter emails before this date
        - sender: Filter by sender email (partial match)
        - tags: Filter by required tags (list)
        - min_score: Minimum relevance score

        Args:
            ranked_emails: List of (email_id, score) tuples
            filters: Filter dictionary

        Returns:
            Filtered list of (email_id, score) tuples
        """
        filtered = []

        for email_id, score in ranked_emails:
            # Min score filter
            if 'min_score' in filters:
                if score < filters['min_score']:
                    continue

            # Get email data
            email_data = self.db.get_email(email_id)
            if not email_data:
                continue

            # Date range filters
            if 'start_date' in filters:
                if email_data['received_time'] and email_data['received_time'] < filters['start_date']:
                    continue

            if 'end_date' in filters:
                if email_data['received_time'] and email_data['received_time'] > filters['end_date']:
                    continue

            # Sender filter
            if 'sender' in filters:
                sender_filter = filters['sender'].lower()
                sender_email = (email_data['sender_email'] or '').lower()
                sender_name = (email_data['sender_name'] or '').lower()

                if sender_filter not in sender_email and sender_filter not in sender_name:
                    continue

            # Tag filter
            if 'tags' in filters:
                classifications = self.db.get_classifications_for_email(email_id)
                email_tags = {c['tag_name'] for c in classifications}
                required_tags = set(filters['tags'])

                # Check if all required tags are present
                if not required_tags.issubset(email_tags):
                    continue

            # Passed all filters
            filtered.append((email_id, score))

        return filtered

    def _log_search(self, query: str, results: List[Dict], top_k: int):
        """Log search to database for analytics."""
        try:
            result_summary = [
                {
                    'email_id': r['email_id'],
                    'score': r['relevance_score'],
                    'subject': r['subject'][:50]  # Truncate for storage
                }
                for r in results
            ]

            self.db.connection.execute("""
                INSERT INTO search_history (query_text, top_k, results)
                VALUES (?, ?, ?)
            """, (query, top_k, json.dumps(result_summary)))

            self.db.connection.commit()
        except Exception as e:
            # Don't fail search if logging fails
            logger.warning(f"Failed to log search: {e}")

    def get_search_history(self, limit: int = 10) -> List[Dict]:
        """
        Get recent search history.

        Args:
            limit: Maximum number of searches to return

        Returns:
            List of search history entries
        """
        cursor = self.db.connection.execute("""
            SELECT * FROM search_history
            ORDER BY search_timestamp DESC
            LIMIT ?
        """, (limit,))

        history = []
        for row in cursor.fetchall():
            entry = dict(row)
            # Parse JSON results
            if entry['results']:
                try:
                    entry['results'] = json.loads(entry['results'])
                except (json.JSONDecodeError, TypeError, ValueError):
                    entry['results'] = []
            history.append(entry)

        return history

    def download_email_from_outlook(self, email_id: int) -> Optional[Dict]:
        """
        Retrieve email from Outlook by conversation ID.
        Useful for getting latest version or full thread.

        Args:
            email_id: Email ID from database

        Returns:
            Email data from Outlook or None
        """
        if not self.email_client:
            logger.warning("Email client not available")
            return None

        email_data = self.db.get_email(email_id)
        if not email_data:
            return None

        conversation_id = email_data['conversation_id']

        try:
            # Search Outlook for this conversation
            # This would require EmailClient implementation
            # For now, return database data
            return email_data
        except Exception as e:
            logger.error(f"Error retrieving from Outlook: {e}")
            return email_data

    def get_similar_emails(self, email_id: int, top_k: int = 5) -> List[Dict]:
        """
        Find emails similar to a given email.

        Args:
            email_id: Reference email ID
            top_k: Number of similar emails to return

        Returns:
            List of similar emails
        """
        # Get email data
        email = self.db.get_email(email_id)
        if not email:
            return []

        # Use email body as query
        query_text = email['body'][:1000]  # Use first 1000 chars

        # Search (excluding the reference email)
        results = self.search(query_text, top_k=top_k + 1)

        # Filter out the reference email
        similar = [r for r in results if r['email_id'] != email_id][:top_k]

        return similar


# Convenience function
def create_search_engine(vector_store, db, email_client=None) -> SearchEngine:
    """
    Create SearchEngine instance.

    Args:
        vector_store: VectorStore instance
        db: DatabaseManager instance
        email_client: Optional EmailClient instance

    Returns:
        SearchEngine instance
    """
    return SearchEngine(vector_store, db, email_client)
