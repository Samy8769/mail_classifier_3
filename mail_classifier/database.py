"""
Database connection and ORM abstraction for mail classifier.
Supports SQLite with filesystem-based vector storage.
"""

import sqlite3
import json
import os
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime
from .logger import get_logger

logger = get_logger('database')


class DatabaseManager:
    """
    Centralized database management.
    Handles connections, migrations, and basic CRUD operations.
    """

    def __init__(self, db_path: str = "mail_classifier.db"):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.connection = None
        self._initialize_database()

    def _initialize_database(self):
        """Create database and tables if not exists."""
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row  # Dict-like access

        # Enable foreign keys
        self.connection.execute("PRAGMA foreign_keys = ON")

        # Enable WAL mode for better concurrency and reliability
        self.connection.execute("PRAGMA journal_mode = WAL")

        # Check if tables exist
        cursor = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='emails'"
        )
        if cursor.fetchone() is None:
            self._create_schema()

    def _create_schema(self):
        """Create database schema from SQL file."""
        schema_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "migrations",
            "001_initial_schema.sql"
        )

        if not os.path.exists(schema_path):
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()

        self.connection.executescript(schema_sql)
        self.connection.commit()
        logger.info(f"Database schema created at: {self.db_path}")

    @contextmanager
    def transaction(self):
        """Context manager for transactions."""
        try:
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    # ==================== Email Operations ====================

    @staticmethod
    def _convert_datetime(value):
        """
        Convert any datetime-like object to ISO format string for SQLite.
        Handles pywintypes.datetime from Outlook COM, Python datetime, etc.

        Args:
            value: A datetime-like object or string

        Returns:
            ISO format string or None
        """
        if value is None:
            return None
        if isinstance(value, str):
            return value
        # Handle pywintypes.datetime and Python datetime
        try:
            return value.strftime('%Y-%m-%d %H:%M:%S')
        except (AttributeError, TypeError):
            return str(value)

    def insert_email(self, email_data: Dict[str, Any]) -> int:
        """
        Insert email into database.

        Args:
            email_data: Dictionary with email fields

        Returns:
            email_id of inserted email
        """
        # Convert received_time to string to avoid pywintypes.datetime binding error
        received_time = self._convert_datetime(email_data.get('received_time'))

        cursor = self.connection.execute("""
            INSERT INTO emails (
                conversation_id, subject, sender_email, sender_name,
                recipients, body, received_time, conversation_topic,
                outlook_categories
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            email_data['conversation_id'],
            email_data.get('subject', ''),
            email_data.get('sender_email', ''),
            email_data.get('sender_name', ''),
            email_data.get('recipients', ''),
            email_data['body'],
            received_time,
            email_data.get('conversation_topic', ''),
            email_data.get('outlook_categories', '')
        ))
        self.connection.commit()
        return cursor.lastrowid

    def get_email(self, email_id: int) -> Optional[Dict]:
        """Retrieve email by ID."""
        cursor = self.connection.execute(
            "SELECT * FROM emails WHERE email_id = ?", (email_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_emails_by_conversation(self, conversation_id: str) -> List[Dict]:
        """Get all emails in a conversation."""
        cursor = self.connection.execute(
            "SELECT * FROM emails WHERE conversation_id = ? ORDER BY received_time",
            (conversation_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def email_exists(self, conversation_id: str) -> bool:
        """Check if email with conversation_id exists."""
        cursor = self.connection.execute(
            "SELECT 1 FROM emails WHERE conversation_id = ? LIMIT 1",
            (conversation_id,)
        )
        return cursor.fetchone() is not None

    # ==================== Chunk Operations ====================

    def insert_chunk(self, chunk_data: Dict[str, Any]) -> int:
        """Insert email chunk."""
        cursor = self.connection.execute("""
            INSERT INTO email_chunks (
                email_id, chunk_index, chunk_text, token_count,
                chunk_type, previous_chunk_overlap
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            chunk_data['email_id'],
            chunk_data['chunk_index'],
            chunk_data['chunk_text'],
            chunk_data['token_count'],
            chunk_data['chunk_type'],
            chunk_data.get('previous_overlap')
        ))
        self.connection.commit()
        return cursor.lastrowid

    def get_chunks_for_email(self, email_id: int) -> List[Dict]:
        """Get all chunks for an email."""
        cursor = self.connection.execute(
            "SELECT * FROM email_chunks WHERE email_id = ? ORDER BY chunk_index",
            (email_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_chunk(self, chunk_id: int) -> Optional[Dict]:
        """Get a specific chunk."""
        cursor = self.connection.execute(
            "SELECT * FROM email_chunks WHERE chunk_id = ?", (chunk_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    # ==================== Embedding Operations ====================

    def insert_embedding_metadata(self, chunk_id: int, embedding_path: str,
                                   model: str, dimension: int) -> int:
        """Insert embedding metadata (actual embedding on filesystem)."""
        cursor = self.connection.execute("""
            INSERT INTO embeddings (chunk_id, embedding_path, embedding_model, embedding_dim)
            VALUES (?, ?, ?, ?)
        """, (chunk_id, embedding_path, model, dimension))
        self.connection.commit()
        return cursor.lastrowid

    def get_embedding_metadata(self, chunk_id: int) -> Optional[Dict]:
        """Get embedding metadata for a chunk."""
        cursor = self.connection.execute(
            "SELECT * FROM embeddings WHERE chunk_id = ?", (chunk_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_embeddings_metadata(self) -> List[Dict]:
        """Get all embedding metadata."""
        cursor = self.connection.execute("SELECT * FROM embeddings")
        return [dict(row) for row in cursor.fetchall()]

    # ==================== Tag Operations ====================

    def insert_tag(self, tag_name: str, axis_name: str,
                   prefix: str, description: str = None,
                   metadata: Dict = None) -> int:
        """Insert new tag."""
        cursor = self.connection.execute("""
            INSERT INTO tags (tag_name, axis_name, prefix, description, tag_metadata)
            VALUES (?, ?, ?, ?, ?)
        """, (
            tag_name, axis_name, prefix, description,
            json.dumps(metadata) if metadata else None
        ))
        self.connection.commit()
        return cursor.lastrowid

    def get_tag_by_name(self, tag_name: str) -> Optional[Dict]:
        """Get tag by name."""
        cursor = self.connection.execute(
            "SELECT * FROM tags WHERE tag_name = ? AND is_active = 1",
            (tag_name,)
        )
        row = cursor.fetchone()
        if row:
            result = dict(row)
            if result['tag_metadata']:
                try:
                    result['tag_metadata'] = json.loads(result['tag_metadata'])
                except json.JSONDecodeError:
                    result['tag_metadata'] = None
            return result
        return None

    def get_tags_by_axis(self, axis_name: str) -> List[Dict]:
        """Get all active tags for an axis."""
        cursor = self.connection.execute(
            "SELECT * FROM tags WHERE axis_name = ? AND is_active = 1 ORDER BY tag_name",
            (axis_name,)
        )

        rows = cursor.fetchall()
        results = [dict(row) for row in rows]

        for result in results:
            if result['tag_metadata']:
                try:
                    result['tag_metadata'] = json.loads(result['tag_metadata'])
                except json.JSONDecodeError:
                    result['tag_metadata'] = None
        return results

    def update_tag(self, tag_name: str, **kwargs):
        """Update tag fields."""
        allowed_fields = ['description', 'tag_metadata', 'is_active']
        updates = []
        params = []

        for field, value in kwargs.items():
            if field in allowed_fields and value is not None:
                if field == 'tag_metadata' and isinstance(value, dict):
                    value = json.dumps(value)
                updates.append(f"{field} = ?")
                params.append(value)

        if not updates:
            return

        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(tag_name)

        query = f"UPDATE tags SET {', '.join(updates)} WHERE tag_name = ?"
        self.connection.execute(query, params)
        self.connection.commit()

    def delete_tag(self, tag_name: str, soft_delete: bool = True):
        """Delete tag (soft delete by default)."""
        if soft_delete:
            self.update_tag(tag_name, is_active=0)
        else:
            self.connection.execute("DELETE FROM tags WHERE tag_name = ?", (tag_name,))
            self.connection.commit()

    # ==================== Classification Operations ====================

    def insert_classification(self, email_id: int, tag_id: int,
                             chunk_id: Optional[int] = None,
                             confidence: float = None,
                             classified_by: str = 'llm',
                             llm_model: str = None) -> int:
        """Link email to tag."""
        cursor = self.connection.execute("""
            INSERT INTO tag_classifications (
                email_id, chunk_id, tag_id, confidence_score,
                classified_by, llm_model
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (email_id, chunk_id, tag_id, confidence, classified_by, llm_model))
        self.connection.commit()
        return cursor.lastrowid

    def get_classifications_for_email(self, email_id: int) -> List[Dict]:
        """Get all tag classifications for an email."""
        cursor = self.connection.execute("""
            SELECT tc.*, t.tag_name, t.axis_name, t.prefix
            FROM tag_classifications tc
            JOIN tags t ON tc.tag_id = t.tag_id
            WHERE tc.email_id = ?
            ORDER BY tc.created_at
        """, (email_id,))
        return [dict(row) for row in cursor.fetchall()]

    # ==================== Constraints Operations ====================

    def get_constraints_for_axis(self, axis_name: str) -> List[str]:
        """
        Get all active constraints for an axis.

        Args:
            axis_name: Classification axis name

        Returns:
            List of constraint texts
        """
        try:
            cursor = self.connection.execute("""
                SELECT constraint_text FROM axis_constraints
                WHERE axis_name = ? AND is_active = 1
                ORDER BY constraint_order ASC
            """, (axis_name,))
            return [row['constraint_text'] for row in cursor.fetchall()]
        except Exception as e:
            logger.debug(f"Error fetching constraints for axis '{axis_name}': {e}")
            return []

    def get_all_constraints(self) -> Dict[str, List[str]]:
        """Get all constraints grouped by axis."""
        try:
            cursor = self.connection.execute("""
                SELECT axis_name, constraint_text FROM axis_constraints
                WHERE is_active = 1
                ORDER BY axis_name, constraint_order ASC
            """)
            result = {}
            for row in cursor.fetchall():
                axis = row['axis_name']
                if axis not in result:
                    result[axis] = []
                result[axis].append(row['constraint_text'])
            return result
        except Exception as e:
            logger.debug(f"Error fetching all constraints: {e}")
            return {}

    # ==================== Inference Rules Operations ====================

    def get_inference_rules(self, prefix: str = None) -> List[Dict]:
        """
        Get inference rules, optionally filtered by condition prefix.

        Args:
            prefix: Optional prefix to filter by (e.g., 'AN_')

        Returns:
            List of inference rule dictionaries
        """
        try:
            if prefix:
                cursor = self.connection.execute("""
                    SELECT * FROM inference_rules
                    WHERE condition_prefix = ? AND is_active = 1
                    ORDER BY priority ASC
                """, (prefix,))
            else:
                cursor = self.connection.execute("""
                    SELECT * FROM inference_rules
                    WHERE is_active = 1
                    ORDER BY priority ASC
                """)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.debug(f"Error fetching inference rules: {e}")
            return []

    def apply_inference_rules(self, tags: List[str]) -> List[str]:
        """
        Apply inference rules to a list of tags.

        Args:
            tags: Current list of tags

        Returns:
            Extended list with inferred tags added
        """
        result = list(tags)
        rules = self.get_inference_rules()

        for rule in rules:
            prefix = rule['condition_prefix']
            action = rule['action_type']
            value = rule['action_value']

            # Check if any tag matches the condition prefix
            if any(tag.startswith(prefix) for tag in tags):
                if action == 'add' and value not in result:
                    result.append(value)

        return result

    # ==================== Definitions Operations ====================

    def get_definitions(self, category: str = None) -> List[Dict]:
        """
        Get definitions/glossary entries.

        Args:
            category: Optional category filter

        Returns:
            List of definition dictionaries
        """
        try:
            if category:
                cursor = self.connection.execute("""
                    SELECT term, definition, category FROM definitions
                    WHERE category = ? AND is_active = 1
                    ORDER BY term ASC
                """, (category,))
            else:
                cursor = self.connection.execute("""
                    SELECT term, definition, category FROM definitions
                    WHERE is_active = 1
                    ORDER BY term ASC
                """)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.debug(f"Error fetching definitions: {e}")
            return []

    def get_definition(self, term: str) -> Optional[str]:
        """Get definition for a specific term."""
        try:
            cursor = self.connection.execute(
                "SELECT definition FROM definitions WHERE term = ? AND is_active = 1",
                (term,)
            )
            row = cursor.fetchone()
            return row['definition'] if row else None
        except Exception as e:
            logger.debug(f"Error fetching definition for '{term}': {e}")
            return None

    # ==================== Color Palette Operations ====================

    def get_color_palette(self) -> Dict[str, str]:
        """Get the full color palette."""
        try:
            cursor = self.connection.execute("""
                SELECT prefix_or_tag, color_name FROM color_palette
                WHERE is_active = 1
            """)
            return {row['prefix_or_tag']: row['color_name'] for row in cursor.fetchall()}
        except Exception as e:
            logger.debug(f"Error fetching color palette: {e}")
            return {}

    def get_color_for_tag(self, tag: str) -> Optional[str]:
        """
        Get color for a specific tag.
        Tries exact match first, then prefix match.
        """
        try:
            # Try exact match
            cursor = self.connection.execute(
                "SELECT color_name FROM color_palette WHERE prefix_or_tag = ? AND is_active = 1",
                (tag,)
            )
            row = cursor.fetchone()
            if row:
                return row['color_name']

            # Try prefix match (e.g., tag="T_Qualite" -> prefix="T_")
            if '_' in tag:
                prefix = tag.split('_')[0] + '_'
                cursor = self.connection.execute(
                    "SELECT color_name FROM color_palette WHERE prefix_or_tag = ? AND is_active = 1",
                    (prefix,)
                )
                row = cursor.fetchone()
                if row:
                    return row['color_name']

            return None
        except Exception as e:
            logger.debug(f"Error fetching color for tag '{tag}': {e}")
            return None

    # ==================== Tag Lookup Operations ====================

    def get_all_active_tag_names(self) -> set:
        """
        Get all active tag names as a set for fast lookup.

        Returns:
            Set of all active tag_name strings
        """
        cursor = self.connection.execute(
            "SELECT tag_name FROM tags WHERE is_active = 1"
        )
        return {row['tag_name'] for row in cursor.fetchall()}

    def get_all_active_tags_with_axis(self) -> List[Dict]:
        """
        Get all active tags with their axis and prefix info.

        Returns:
            List of dicts with tag_name, axis_name, prefix
        """
        cursor = self.connection.execute(
            "SELECT tag_name, axis_name, prefix FROM tags WHERE is_active = 1 ORDER BY tag_name"
        )
        return [dict(row) for row in cursor.fetchall()]

    # ==================== Full Rules Reconstruction ====================

    # Related axes mapping: when building rules for an axis,
    # include tags from these related axes as well
    RELATED_AXES = {
        'qualite': ['qualite', 'jalons', 'anomalies', 'nrb'],
    }

    def reconstruct_full_rules(self, axis_name: str) -> str:
        """
        Reconstruct complete rules for an axis from database.
        Replaces loading from regles_mail_*.txt files.

        Args:
            axis_name: Classification axis name

        Returns:
            Formatted rules string for LLM prompt
        """
        parts = []

        # Header
        parts.append(f"# Règles pour l'axe: {axis_name}")
        parts.append(f"# Source: base de données")
        parts.append("")

        # Get axes to query (include related axes if defined)
        axes_to_query = self.RELATED_AXES.get(axis_name, [axis_name])

        # Get tags for this axis and related axes
        tags = []
        for ax in axes_to_query:
            tags.extend(self.get_tags_by_axis(ax))
        if tags:
            # Group by prefix
            by_prefix = {}
            for tag in tags:
                prefix = tag['prefix']
                if prefix not in by_prefix:
                    by_prefix[prefix] = []
                by_prefix[prefix].append(tag)

            parts.append("## Valeurs autorisées:")
            for prefix, prefix_tags in sorted(by_prefix.items()):
                parts.append(f"\n### {prefix}")
                parts.append(f"list_type: closed")
                parts.append("values:")
                for tag in prefix_tags:
                    parts.append(f"  - {tag['tag_name']}")
                    if tag.get('description'):
                        parts.append(f"    # {tag['description']}")

        # Get constraints
        constraints = self.get_constraints_for_axis(axis_name)
        if constraints:
            parts.append("")
            parts.append("## Contraintes:")
            for constraint in constraints:
                parts.append(f"  - \"{constraint}\"")

        # Get relevant definitions
        definitions = self.get_definitions()
        if definitions:
            parts.append("")
            parts.append("## Définitions:")
            for defn in definitions[:10]:  # Limit to avoid prompt bloat
                parts.append(f"  - {defn['term']} = {defn['definition']}")

        return '\n'.join(parts)

    # ==================== Statistics ====================

    def get_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        stats = {}

        cursor = self.connection.execute("SELECT COUNT(*) as count FROM emails")
        stats['emails'] = cursor.fetchone()['count']

        cursor = self.connection.execute("SELECT COUNT(*) as count FROM email_chunks")
        stats['chunks'] = cursor.fetchone()['count']

        cursor = self.connection.execute("SELECT COUNT(*) as count FROM embeddings")
        stats['embeddings'] = cursor.fetchone()['count']

        cursor = self.connection.execute("SELECT COUNT(*) as count FROM tags WHERE is_active = 1")
        stats['active_tags'] = cursor.fetchone()['count']

        cursor = self.connection.execute("SELECT COUNT(*) as count FROM tag_classifications")
        stats['classifications'] = cursor.fetchone()['count']

        return stats

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
