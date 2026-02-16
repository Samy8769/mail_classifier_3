"""
Tag management for database-backed classification rules.
CRUD operations for classification tags.
"""

from typing import List, Dict, Optional, Any
from datetime import datetime
from .database import DatabaseManager
from .logger import get_logger

logger = get_logger('tag_manager')


class TagManager:
    """
    CRUD operations for classification tags.
    Replaces file-based regles_mail_*.txt management.
    """

    # Valid classification axes
    VALID_AXES = [
        'type_mail', 'statut', 'client', 'affaire', 'projet',
        'fournisseur', 'equipement_type', 'equipement_designation',
        'essais', 'technique', 'qualite', 'jalons', 'anomalies', 'nrb'
    ]

    # Prefix mapping for auto-detection
    PREFIX_MAP = {
        'T_': 'type_mail',
        'S_': 'statut',
        'C_': 'client',
        'A_': 'affaire',
        'P_': 'projet',
        'F_': 'fournisseur',
        'EQT_': 'equipement_type',
        'EQ_': 'equipement_designation',
        'E_': 'essais',
        'TC_': 'technique',
        'Q_': 'qualite',
        'J_': 'jalons',
        'AN_': 'anomalies',
        'NRB_': 'nrb',
    }

    def __init__(self, db: DatabaseManager):
        """
        Args:
            db: Database manager instance
        """
        self.db = db

    def add_tag(self, tag_name: str, axis_name: str = None,
                description: str = None,
                metadata: Dict = None) -> int:
        """
        Add new classification tag via CLI.

        Args:
            tag_name: Tag name (e.g., 'T_NewType', 'P_NewProject')
            axis_name: Classification axis ('type', 'projet', etc.). Auto-detected if None.
            description: Optional description
            metadata: Optional metadata dictionary

        Returns:
            tag_id of created tag

        Raises:
            ValueError: If tag already exists or invalid axis
        """
        # Auto-detect axis from prefix if not provided
        if axis_name is None:
            axis_name = self._detect_axis_from_tag(tag_name)
            if axis_name is None:
                raise ValueError(
                    f"Cannot auto-detect axis for tag '{tag_name}'. "
                    f"Please specify axis explicitly. Valid axes: {self.VALID_AXES}"
                )

        # Validate axis
        if axis_name not in self.VALID_AXES:
            raise ValueError(
                f"Invalid axis: {axis_name}. Must be one of {self.VALID_AXES}"
            )

        # Extract prefix from tag name
        prefix = self._extract_prefix(tag_name)

        # Check if tag exists
        existing = self.db.get_tag_by_name(tag_name)
        if existing:
            if existing['is_active']:
                raise ValueError(f"Tag '{tag_name}' already exists")
            else:
                # Reactivate inactive tag
                self.db.update_tag(tag_name, is_active=1, description=description)
                logger.info(f"Tag '{tag_name}' reactivated")
                return existing['tag_id']

        # Insert tag
        tag_id = self.db.insert_tag(
            tag_name=tag_name,
            axis_name=axis_name,
            prefix=prefix,
            description=description,
            metadata=metadata
        )

        logger.info(f"Tag '{tag_name}' added to axis '{axis_name}' (ID: {tag_id})")
        return tag_id

    def _detect_axis_from_tag(self, tag_name: str) -> Optional[str]:
        """Auto-detect axis from tag prefix."""
        # Check multi-char prefixes first (EQT_, NRB_, AN_, TC_, EQ_)
        # Sorted by length descending to match longest prefix first
        for prefix in sorted(self.PREFIX_MAP.keys(), key=len, reverse=True):
            if tag_name.startswith(prefix):
                return self.PREFIX_MAP[prefix]

        return None

    def _extract_prefix(self, tag_name: str) -> str:
        """Extract prefix from tag name."""
        # Single-char prefix
        if len(tag_name) >= 2 and tag_name[1] == '_':
            return tag_name[:2]

        # Multi-char prefix (e.g., Proc_)
        if '_' in tag_name:
            parts = tag_name.split('_')
            return parts[0] + '_'

        # Default: first char + underscore
        return tag_name[0] + '_' if tag_name else ''

    def list_tags(self, axis_name: Optional[str] = None,
                  prefix: Optional[str] = None,
                  active_only: bool = True) -> List[Dict]:
        """
        List tags with optional filtering.

        Args:
            axis_name: Filter by axis
            prefix: Filter by prefix
            active_only: Only return active tags

        Returns:
            List of tag dictionaries
        """
        query = "SELECT * FROM tags WHERE 1=1"
        params = []

        if axis_name:
            query += " AND axis_name = ?"
            params.append(axis_name)

        if prefix:
            query += " AND prefix = ?"
            params.append(prefix)

        if active_only:
            query += " AND is_active = 1"

        query += " ORDER BY axis_name, tag_name"

        cursor = self.db.connection.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def update_tag(self, tag_name: str,
                   description: str = None,
                   metadata: Dict = None,
                   is_active: bool = None):
        """
        Update existing tag.

        Args:
            tag_name: Tag to update
            description: New description
            metadata: New metadata
            is_active: Activate/deactivate tag
        """
        kwargs = {}
        if description is not None:
            kwargs['description'] = description
        if metadata is not None:
            kwargs['tag_metadata'] = metadata
        if is_active is not None:
            kwargs['is_active'] = 1 if is_active else 0

        if not kwargs:
            logger.info(f"No changes specified for tag '{tag_name}'")
            return

        self.db.update_tag(tag_name, **kwargs)
        logger.info(f"Tag '{tag_name}' updated")

    def delete_tag(self, tag_name: str, hard_delete: bool = False):
        """
        Delete tag (soft delete by default).

        Args:
            tag_name: Tag to delete
            hard_delete: If True, permanently delete; if False, deactivate
        """
        if hard_delete:
            self.db.delete_tag(tag_name, soft_delete=False)
            logger.info(f"Tag '{tag_name}' deleted permanently")
        else:
            self.db.delete_tag(tag_name, soft_delete=True)
            logger.info(f"Tag '{tag_name}' deactivated")

    def export_tags_to_yaml(self, axis_name: str, output_path: str):
        """
        Export tags back to YAML format for backup/review.

        Args:
            axis_name: Axis to export
            output_path: Output file path
        """
        import yaml

        tags = self.db.get_tags_by_axis(axis_name)

        if not tags:
            logger.info(f"No tags found for axis '{axis_name}'")
            return

        # Build YAML structure
        yaml_data = {
            'axis': axis_name,
            'exported_at': str(datetime.now()),
            'tag_count': len(tags),
            'tags': [
                {
                    'name': tag['tag_name'],
                    'prefix': tag['prefix'],
                    'description': tag['description'],
                    'active': bool(tag['is_active'])
                }
                for tag in tags
            ]
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(yaml_data, f, allow_unicode=True, sort_keys=False)

        logger.info(f"Exported {len(tags)} tags to {output_path}")

    def import_tags_from_yaml(self, yaml_path: str, axis_name: str) -> int:
        """
        Import tags from YAML file.

        Args:
            yaml_path: Path to YAML file
            axis_name: Target axis name

        Returns:
            Number of tags imported
        """
        import yaml

        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not data or 'tags' not in data:
            logger.warning(f"Invalid YAML format in {yaml_path}")
            return 0

        imported = 0
        for tag_data in data['tags']:
            try:
                tag_name = tag_data['name']
                self.add_tag(
                    tag_name=tag_name,
                    axis_name=axis_name,
                    description=tag_data.get('description')
                )
                imported += 1
            except ValueError as e:
                logger.warning(f"Skipped {tag_name}: {e}")
            except Exception as e:
                logger.error(f"Error importing {tag_name}: {e}")

        logger.info(f"Imported {imported} tags from {yaml_path}")
        return imported

    def get_tag_statistics(self) -> Dict[str, Any]:
        """Get statistics about tags."""
        stats = {
            'total_tags': 0,
            'active_tags': 0,
            'inactive_tags': 0,
            'by_axis': {}
        }

        cursor = self.db.connection.execute(
            "SELECT axis_name, is_active, COUNT(*) as count "
            "FROM tags GROUP BY axis_name, is_active"
        )

        for row in cursor:
            axis = row['axis_name']
            is_active = row['is_active']
            count = row['count']

            stats['total_tags'] += count

            if is_active:
                stats['active_tags'] += count
            else:
                stats['inactive_tags'] += count

            if axis not in stats['by_axis']:
                stats['by_axis'][axis] = {'active': 0, 'inactive': 0}

            if is_active:
                stats['by_axis'][axis]['active'] += count
            else:
                stats['by_axis'][axis]['inactive'] += count

        return stats



