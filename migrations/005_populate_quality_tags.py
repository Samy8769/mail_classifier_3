#!/usr/bin/env python3
"""
Migration script: Quality tags from regles_mail_qualite.txt -> SQLite

Populates quality-related tags (Q_, J_, AN_, NRB_), their inference rules,
constraints, definitions, and color palette into the database.

Source file: config/regles_mail_qualite.txt (or regles_mail_qualité.txt)

Usage:
    python migrations/005_populate_quality_tags.py [--db-path path/to/db]
"""

import sqlite3
import re
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class QualityTagsMigrator:
    """Migrates quality tags from regles_mail_qualite.txt to SQLite database."""

    # Quality-related axes and their prefixes
    QUALITY_AXES = {
        'qualite': 'Q_',
        'jalons': 'J_',
        'anomalies': 'AN_',
        'nrb': 'NRB_',
    }

    # Source file candidates (try without accent first, then with)
    SOURCE_FILES = [
        'regles_mail_qualité.txt',
        'regles_mail_qualite.txt',
    ]

    def __init__(self, db_path: str, config_dir: str):
        self.db_path = db_path
        self.config_dir = Path(config_dir)
        self.conn = None
        self.stats = {
            'tags_inserted': 0,
            'tags_skipped': 0,
            'constraints': 0,
            'inference_rules': 0,
            'definitions': 0,
            'colors': 0,
            'errors': []
        }

    def connect(self):
        """Connect to database."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def _find_source_file(self) -> Optional[Path]:
        """Find the quality rules source file."""
        for filename in self.SOURCE_FILES:
            filepath = self.config_dir / filename
            if filepath.exists():
                return filepath
        return None

    def _ensure_schema(self):
        """Ensure required tables exist (run 003 migration if needed)."""
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='axis_constraints'"
        )
        if cursor.fetchone() is None:
            schema_path = Path(__file__).parent / '003_migrate_rules_to_db.sql'
            if schema_path.exists():
                with open(schema_path, 'r', encoding='utf-8') as f:
                    self.conn.executescript(f.read())
                self.conn.commit()
                print("  Schema tables created (axis_constraints, inference_rules, etc.)")
            else:
                raise FileNotFoundError(
                    f"Schema migration not found: {schema_path}. "
                    "Run 003_migrate_rules_to_db.sql first."
                )

    def parse_quality_rules(self, content: str) -> Dict[str, Any]:
        """
        Parse the quality rules file content.

        Returns dict with:
            axes: {axis_name: {prefix, values, description, rules}}
            constraints: [str]
            inference_rules: [{condition, action_type, action_value}]
            definitions: [{term, definition}]
            color_palette: {prefix_or_tag: color}
        """
        result = {
            'axes': {},
            'constraints': [],
            'inference_rules': [],
            'definitions': [],
            'color_palette': {}
        }

        # Extract axes with their values
        # Handles: qualité:\n  prefix: "Q_"\n  description: "..."\n  values:\n    - Value1
        axis_pattern = (
            r'(\w+[\w\u00e9]*):\s*\n'
            r'\s+prefix:\s*["\']?([A-Z]+_)["\']?\s*\n'
            r'\s+description:\s*["\']?(.+?)["\']?\s*\n'
            r'(?:.*?\n)*?'
            r'\s+values:\s*\n'
            r'((?:\s+-\s+[^\n]+\n?)+)'
        )
        for match in re.finditer(axis_pattern, content, re.MULTILINE):
            raw_name = match.group(1)
            prefix = match.group(2)
            description = match.group(3).strip()
            values_block = match.group(4)

            # Normalize axis name (qualité -> qualite, etc.)
            axis_name = self._normalize_axis_name(raw_name, prefix)

            # Extract values
            values = []
            for value_match in re.finditer(r'-\s+([^\n#]+)', values_block):
                value = value_match.group(1).strip()
                if value and not value.startswith('#'):
                    values.append(value)

            # Extract per-axis rules if present
            rules = []
            rules_pattern = (
                rf'{re.escape(raw_name)}:.*?rules:\s*\n((?:\s+-\s+["\'][^\n]+["\']\s*\n?)+)'
            )
            rules_match = re.search(rules_pattern, content, re.DOTALL)
            if rules_match:
                for r_match in re.finditer(r'-\s+["\'](.+?)["\']', rules_match.group(1)):
                    rules.append(r_match.group(1))

            result['axes'][axis_name] = {
                'prefix': prefix,
                'description': description,
                'values': values,
                'rules': rules,
            }

        # Extract inference rules
        inference_section = re.search(
            r'inference_rules:\s*\n((?:\s+-\s+if:.*\n(?:\s+then:.*\n(?:\s+-\s+\w+:.*\n?)*)*)+)',
            content, re.MULTILINE
        )
        if inference_section:
            rules_block = inference_section.group(1)
            for rule_match in re.finditer(
                r'-\s+if:\s*["\']?(.+?)["\']?\s*\n\s+then:\s*\n((?:\s+-\s+\w+:.+\n?)+)',
                rules_block
            ):
                condition = rule_match.group(1).strip().strip('"\'')
                actions_block = rule_match.group(2)
                for action_match in re.finditer(
                    r'-\s+(\w+):\s*["\']?(.+?)["\']?\s*$',
                    actions_block, re.MULTILINE
                ):
                    result['inference_rules'].append({
                        'condition': condition,
                        'action_type': action_match.group(1),
                        'action_value': action_match.group(2).strip().strip('"\'')
                    })

        # Extract constraints
        constraints_match = re.search(
            r'constraints:\s*\n((?:\s+-\s+["\'].+["\']\s*\n?)+)', content
        )
        if constraints_match:
            for c_match in re.finditer(r'-\s+["\'](.+?)["\']', constraints_match.group(1)):
                result['constraints'].append(c_match.group(1))

        # Extract definitions
        definitions_match = re.search(
            r'[Dd]efinitions:\s*\n((?:\s+-\s+["\'].+["\']\s*\n?)+)', content
        )
        if definitions_match:
            for d_match in re.finditer(
                r'-\s+["\'](.+?)\s*=\s*(.+?)["\']',
                definitions_match.group(1)
            ):
                result['definitions'].append({
                    'term': d_match.group(1).strip(),
                    'definition': d_match.group(2).strip()
                })

        # Extract color palette
        colors_match = re.search(
            r'color_palette:\s*\n((?:\s+\S+:\s*["\']?\w+["\']?\s*\n?)+)', content
        )
        if colors_match:
            for c_match in re.finditer(r'(\S+):\s*["\']?(\w+)["\']?', colors_match.group(1)):
                result['color_palette'][c_match.group(1)] = c_match.group(2)

        return result

    def _normalize_axis_name(self, raw_name: str, prefix: str) -> str:
        """Map raw axis name to normalized DB axis name using prefix."""
        prefix_to_axis = {v: k for k, v in self.QUALITY_AXES.items()}
        if prefix in prefix_to_axis:
            return prefix_to_axis[prefix]
        # Fallback: normalize accented characters
        normalized = raw_name.replace('é', 'e').replace('è', 'e').lower()
        if normalized in self.QUALITY_AXES:
            return normalized
        return raw_name.lower()

    def _insert_tag(self, tag_name: str, axis_name: str, prefix: str,
                    description: str = None):
        """Insert a single tag, skip if exists."""
        try:
            cursor = self.conn.execute(
                "SELECT tag_id, is_active FROM tags WHERE tag_name = ?",
                (tag_name,)
            )
            existing = cursor.fetchone()

            if existing:
                if not existing['is_active']:
                    self.conn.execute(
                        "UPDATE tags SET is_active = 1, axis_name = ?, prefix = ?, "
                        "description = ?, updated_at = ? WHERE tag_name = ?",
                        (axis_name, prefix, description,
                         datetime.now().isoformat(), tag_name)
                    )
                    self.stats['tags_inserted'] += 1
                else:
                    self.stats['tags_skipped'] += 1
            else:
                self.conn.execute("""
                    INSERT INTO tags (tag_name, axis_name, prefix, description, is_active)
                    VALUES (?, ?, ?, ?, 1)
                """, (tag_name, axis_name, prefix, description))
                self.stats['tags_inserted'] += 1
        except Exception as e:
            self.stats['errors'].append(f"Tag {tag_name}: {e}")

    def _insert_constraint(self, axis_name: str, constraint_text: str, order: int):
        """Insert a constraint if not exists."""
        try:
            cursor = self.conn.execute(
                "SELECT constraint_id FROM axis_constraints "
                "WHERE axis_name = ? AND constraint_text = ?",
                (axis_name, constraint_text)
            )
            if not cursor.fetchone():
                self.conn.execute("""
                    INSERT INTO axis_constraints
                    (axis_name, constraint_text, constraint_order, is_active)
                    VALUES (?, ?, ?, 1)
                """, (axis_name, constraint_text, order))
                self.stats['constraints'] += 1
        except Exception as e:
            self.stats['errors'].append(f"Constraint: {e}")

    def _insert_inference_rule(self, condition_prefix: str, action_type: str,
                                action_value: str, description: str = None):
        """Insert an inference rule if not exists."""
        try:
            cursor = self.conn.execute(
                "SELECT rule_id FROM inference_rules "
                "WHERE condition_prefix = ? AND action_value = ?",
                (condition_prefix, action_value)
            )
            if not cursor.fetchone():
                self.conn.execute("""
                    INSERT INTO inference_rules
                    (condition_prefix, condition_type, action_type, action_value,
                     description, is_active)
                    VALUES (?, 'present', ?, ?, ?, 1)
                """, (condition_prefix, action_type, action_value, description))
                self.stats['inference_rules'] += 1
        except Exception as e:
            self.stats['errors'].append(f"Inference rule: {e}")

    def _insert_definition(self, term: str, definition: str):
        """Insert a definition."""
        try:
            self.conn.execute("""
                INSERT OR REPLACE INTO definitions (term, definition, category, is_active)
                VALUES (?, ?, 'qualite', 1)
            """, (term, definition))
            self.stats['definitions'] += 1
        except Exception as e:
            self.stats['errors'].append(f"Definition {term}: {e}")

    def _insert_color(self, prefix_or_tag: str, color_name: str,
                      axis_name: str = None):
        """Insert a color mapping."""
        try:
            self.conn.execute("""
                INSERT OR REPLACE INTO color_palette
                (prefix_or_tag, color_name, axis_name, is_active)
                VALUES (?, ?, ?, 1)
            """, (prefix_or_tag, color_name, axis_name))
            self.stats['colors'] += 1
        except Exception as e:
            self.stats['errors'].append(f"Color {prefix_or_tag}: {e}")

    def run(self):
        """Run the quality tags migration."""
        print("=" * 60)
        print("Mail Classifier - Quality Tags Migration (005)")
        print("=" * 60)
        print(f"Database: {self.db_path}")
        print(f"Config dir: {self.config_dir}")

        # Find source file
        source = self._find_source_file()
        if not source:
            print(f"\nERROR: Quality rules file not found in {self.config_dir}")
            print(f"  Tried: {', '.join(self.SOURCE_FILES)}")
            return False

        print(f"Source: {source.name}")
        print()

        # Connect and ensure schema
        self.connect()
        self._ensure_schema()

        # Read and parse
        with open(source, 'r', encoding='utf-8') as f:
            content = f.read()

        data = self.parse_quality_rules(content)

        # --- Insert tags ---
        print("Inserting quality tags...")
        for axis_name, axis_data in data['axes'].items():
            prefix = axis_data['prefix']
            description = axis_data.get('description', '')

            # Only process quality-related axes
            if axis_name not in self.QUALITY_AXES:
                print(f"  Skipping non-quality axis: {axis_name}")
                continue

            print(f"  Axis: {axis_name} ({prefix})")
            for value in axis_data['values']:
                # Build full tag name
                if value.startswith(prefix):
                    tag_name = value
                else:
                    tag_name = f"{prefix}{value}"

                self._insert_tag(tag_name, axis_name, prefix, description)
                print(f"    + {tag_name}")

        # --- Insert constraints (apply to qualite parent axis) ---
        print("\nInserting constraints...")
        quality_axes = list(self.QUALITY_AXES.keys())
        for idx, constraint in enumerate(data['constraints']):
            for axis in quality_axes:
                self._insert_constraint(axis, constraint, idx)
            print(f"  + {constraint[:60]}...")

        # --- Insert inference rules ---
        print("\nInserting inference rules...")
        for rule in data['inference_rules']:
            condition = rule['condition']
            prefix_match = re.search(r'([A-Z]+_)', condition)
            if prefix_match:
                prefix = prefix_match.group(1)
                self._insert_inference_rule(
                    prefix,
                    rule['action_type'],
                    rule['action_value'],
                    f"Quality rule: if {condition}"
                )
                print(f"  + if {condition} -> {rule['action_type']} {rule['action_value']}")

        # --- Insert definitions ---
        print("\nInserting definitions...")
        for defn in data['definitions']:
            self._insert_definition(defn['term'], defn['definition'])
            print(f"  + {defn['term']} = {defn['definition'][:50]}...")

        # --- Insert colors ---
        print("\nInserting color palette...")
        for prefix_or_tag, color in data['color_palette'].items():
            # Determine axis from prefix
            axis = None
            for ax, px in self.QUALITY_AXES.items():
                if prefix_or_tag == px or prefix_or_tag.startswith(px):
                    axis = ax
                    break
            self._insert_color(prefix_or_tag, color, axis)
            print(f"  + {prefix_or_tag} -> {color}")

        # Commit
        self.conn.commit()
        self.close()

        # Summary
        print("\n" + "=" * 60)
        print("Migration Summary")
        print("=" * 60)
        print(f"  Tags inserted:            {self.stats['tags_inserted']}")
        print(f"  Tags skipped (existing):  {self.stats['tags_skipped']}")
        print(f"  Constraints:              {self.stats['constraints']}")
        print(f"  Inference rules:          {self.stats['inference_rules']}")
        print(f"  Definitions:              {self.stats['definitions']}")
        print(f"  Colors:                   {self.stats['colors']}")

        if self.stats['errors']:
            print(f"\n  Errors: {len(self.stats['errors'])}")
            for error in self.stats['errors'][:10]:
                print(f"    - {error}")
            if len(self.stats['errors']) > 10:
                print(f"    ... and {len(self.stats['errors']) - 10} more")
        else:
            print("\n  No errors!")

        print("\nMigration complete!")
        return len(self.stats['errors']) == 0


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Migrate quality tags to database'
    )
    parser.add_argument('--db-path', default='mail_classifier.db',
                        help='Path to SQLite database')
    parser.add_argument('--config-dir', default='config',
                        help='Path to config directory with rules files')

    args = parser.parse_args()

    # Resolve paths relative to project root
    project_root = Path(__file__).parent.parent
    db_path = project_root / args.db_path
    config_dir = project_root / args.config_dir

    migrator = QualityTagsMigrator(str(db_path), str(config_dir))
    success = migrator.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
