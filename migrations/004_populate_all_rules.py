#!/usr/bin/env python3
"""
Migration script: regles_mail_*.txt -> SQLite

Migrates all rules, constraints, definitions, and colors from YAML files to database.
Run this script once after creating the new tables with 003_migrate_rules_to_db.sql.

Usage:
    python migrations/004_populate_all_rules.py [--db-path path/to/db]
"""

import sqlite3
import re
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class RulesMigrator:
    """Migrates rules from YAML files to SQLite database."""

    # Mapping of axis names to their expected prefixes
    AXIS_PREFIX_MAP = {
        'type': ['T_', 'S_'],
        'projet': ['P_', 'C_', 'A_'],
        'fournisseur': ['F_'],
        'equipement_type': ['EQT_'],
        'equipement_designation': ['EQ_'],
        'processus': ['E_', 'TC_'],
        'qualite': ['Q_'],
        'jalons': ['J_'],
        'anomalies': ['AN_'],
        'nrb': ['NRB_'],
    }

    # Files to process and their axis mappings
    FILES_CONFIG = {
        'regles_mail_type.txt': ['type'],
        'regles_mail_projet.txt': ['projet'],
        'regles_mail_fournisseur.txt': ['fournisseur'],
        'regles_mail_equipement_type.txt': ['equipement_type'],
        'regles_mail_equipement_designation.txt': ['equipement_designation'],
        'regles_mail_processus.txt': ['processus'],
        'regles_mail_qualité.txt': ['qualite', 'jalons', 'anomalies', 'nrb'],
    }

    def __init__(self, db_path: str, config_dir: str):
        self.db_path = db_path
        self.config_dir = Path(config_dir)
        self.conn = None
        self.stats = {
            'tags': 0,
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

    def run_schema_migration(self):
        """Run the SQL schema migration."""
        schema_path = Path(__file__).parent / '003_migrate_rules_to_db.sql'
        if schema_path.exists():
            with open(schema_path, 'r', encoding='utf-8') as f:
                self.conn.executescript(f.read())
            self.conn.commit()
            print("Schema migration completed.")
        else:
            print(f"Warning: Schema file not found: {schema_path}")

    def parse_yaml_content(self, content: str) -> Dict[str, Any]:
        """
        Parse YAML-like content from rules files.
        These files are not strict YAML, so we use regex parsing.
        """
        result = {
            'axes': {},
            'constraints': [],
            'inference_rules': [],
            'definitions': [],
            'color_palette': {}
        }

        # Extract axes with their values
        # Pattern: axis_name:\n  prefix: "X_"\n  values:\n    - Value1
        axis_pattern = r'(\w+):\s*\n\s+prefix:\s*["\']?([A-Z]+_)["\']?\s*\n.*?values:\s*\n((?:\s+-\s+.+\n?)+)'
        for match in re.finditer(axis_pattern, content, re.MULTILINE | re.DOTALL):
            axis_name = match.group(1)
            prefix = match.group(2)
            values_block = match.group(3)

            # Extract individual values
            values = []
            for value_match in re.finditer(r'-\s+([^\n#]+)', values_block):
                value = value_match.group(1).strip()
                if value and not value.startswith('#'):
                    values.append(value)

            result['axes'][axis_name] = {
                'prefix': prefix,
                'values': values
            }

        # Extract constraints
        constraints_match = re.search(r'constraints:\s*\n((?:\s+-\s+["\'].+["\']\s*\n?)+)', content)
        if constraints_match:
            for c_match in re.finditer(r'-\s+["\'](.+?)["\']', constraints_match.group(1)):
                result['constraints'].append(c_match.group(1))

        # Extract inference rules
        inference_match = re.search(r'inference_rules:\s*\n((?:\s+-\s+if:.+\n(?:\s+then:.+\n?)+)+)', content, re.MULTILINE)
        if inference_match:
            rules_block = inference_match.group(1)
            # Parse each rule
            for rule_match in re.finditer(r'-\s+if:\s*["\']?(.+?)["\']?\s*\n\s+then:\s*\n((?:\s+-\s+\w+:.+\n?)+)', rules_block):
                condition = rule_match.group(1).strip().strip('"\'')
                actions_block = rule_match.group(2)

                for action_match in re.finditer(r'-\s+(\w+):\s*["\']?(.+?)["\']?\s*$', actions_block, re.MULTILINE):
                    result['inference_rules'].append({
                        'condition': condition,
                        'action_type': action_match.group(1),
                        'action_value': action_match.group(2).strip().strip('"\'')
                    })

        # Extract definitions
        definitions_match = re.search(r'[Dd]efinitions:\s*\n((?:\s+-\s+["\'].+["\']\s*\n?)+)', content)
        if definitions_match:
            for d_match in re.finditer(r'-\s+["\'](.+?)\s*=\s*(.+?)["\']', definitions_match.group(1)):
                result['definitions'].append({
                    'term': d_match.group(1).strip(),
                    'definition': d_match.group(2).strip()
                })

        # Extract color palette
        colors_match = re.search(r'color_palette:\s*\n((?:\s+\w+:\s*["\']?\w+["\']?\s*\n?)+)', content)
        if colors_match:
            for c_match in re.finditer(r'(\S+):\s*["\']?(\w+)["\']?', colors_match.group(1)):
                result['color_palette'][c_match.group(1)] = c_match.group(2)

        return result

    def insert_tag(self, tag_name: str, axis_name: str, prefix: str, description: str = None):
        """Insert a tag into the database."""
        try:
            # Check if tag already exists
            cursor = self.conn.execute(
                "SELECT tag_id, is_active FROM tags WHERE tag_name = ?",
                (tag_name,)
            )
            existing = cursor.fetchone()

            if existing:
                if not existing['is_active']:
                    # Reactivate
                    self.conn.execute(
                        "UPDATE tags SET is_active = 1, updated_at = ? WHERE tag_name = ?",
                        (datetime.now().isoformat(), tag_name)
                    )
                    self.stats['tags'] += 1
            else:
                self.conn.execute("""
                    INSERT INTO tags (tag_name, axis_name, prefix, description, is_active)
                    VALUES (?, ?, ?, ?, 1)
                """, (tag_name, axis_name, prefix, description))
                self.stats['tags'] += 1
        except Exception as e:
            self.stats['errors'].append(f"Tag {tag_name}: {e}")

    def insert_constraint(self, axis_name: str, constraint_text: str, order: int = 0):
        """Insert a constraint into the database."""
        try:
            # Check if constraint already exists
            cursor = self.conn.execute(
                "SELECT constraint_id FROM axis_constraints WHERE axis_name = ? AND constraint_text = ?",
                (axis_name, constraint_text)
            )
            if not cursor.fetchone():
                self.conn.execute("""
                    INSERT INTO axis_constraints (axis_name, constraint_text, constraint_order, is_active)
                    VALUES (?, ?, ?, 1)
                """, (axis_name, constraint_text, order))
                self.stats['constraints'] += 1
        except Exception as e:
            self.stats['errors'].append(f"Constraint: {e}")

    def insert_inference_rule(self, condition_prefix: str, action_type: str,
                              action_value: str, description: str = None):
        """Insert an inference rule into the database."""
        try:
            # Check if rule already exists
            cursor = self.conn.execute(
                "SELECT rule_id FROM inference_rules WHERE condition_prefix = ? AND action_value = ?",
                (condition_prefix, action_value)
            )
            if not cursor.fetchone():
                self.conn.execute("""
                    INSERT INTO inference_rules
                    (condition_prefix, condition_type, action_type, action_value, description, is_active)
                    VALUES (?, 'present', ?, ?, ?, 1)
                """, (condition_prefix, action_type, action_value, description))
                self.stats['inference_rules'] += 1
        except Exception as e:
            self.stats['errors'].append(f"Inference rule: {e}")

    def insert_definition(self, term: str, definition: str, category: str = None):
        """Insert a definition into the database."""
        try:
            self.conn.execute("""
                INSERT OR REPLACE INTO definitions (term, definition, category, is_active)
                VALUES (?, ?, ?, 1)
            """, (term, definition, category))
            self.stats['definitions'] += 1
        except Exception as e:
            self.stats['errors'].append(f"Definition {term}: {e}")

    def insert_color(self, prefix_or_tag: str, color_name: str, axis_name: str = None):
        """Insert a color mapping into the database."""
        try:
            self.conn.execute("""
                INSERT OR REPLACE INTO color_palette (prefix_or_tag, color_name, axis_name, is_active)
                VALUES (?, ?, ?, 1)
            """, (prefix_or_tag, color_name, axis_name))
            self.stats['colors'] += 1
        except Exception as e:
            self.stats['errors'].append(f"Color {prefix_or_tag}: {e}")

    def determine_axis_for_prefix(self, prefix: str) -> str:
        """Determine the axis name for a given prefix."""
        for axis, prefixes in self.AXIS_PREFIX_MAP.items():
            if prefix in prefixes:
                return axis
        return 'unknown'

    def migrate_file(self, filename: str, expected_axes: List[str]):
        """Migrate a single rules file."""
        filepath = self.config_dir / filename
        if not filepath.exists():
            print(f"  Skipping (not found): {filename}")
            return

        print(f"  Processing: {filename}")

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        data = self.parse_yaml_content(content)

        # Insert tags from axes
        for axis_name, axis_data in data['axes'].items():
            prefix = axis_data['prefix']
            mapped_axis = self.determine_axis_for_prefix(prefix)

            for value in axis_data['values']:
                # Construct full tag name
                if value.startswith(prefix):
                    tag_name = value
                else:
                    tag_name = f"{prefix}{value}"

                self.insert_tag(tag_name, mapped_axis, prefix)

        # Insert constraints (apply to all expected axes)
        for idx, constraint in enumerate(data['constraints']):
            for axis in expected_axes:
                self.insert_constraint(axis, constraint, idx)

        # Insert inference rules
        for rule in data['inference_rules']:
            # Extract prefix from condition (e.g., "AN_ present" -> "AN_")
            condition = rule['condition']
            prefix_match = re.search(r'([A-Z]+_)', condition)
            if prefix_match:
                prefix = prefix_match.group(1)
                self.insert_inference_rule(
                    prefix,
                    rule['action_type'],
                    rule['action_value'],
                    f"From {filename}: if {condition}"
                )

        # Insert definitions
        for defn in data['definitions']:
            self.insert_definition(defn['term'], defn['definition'])

        # Insert colors
        for prefix_or_tag, color in data['color_palette'].items():
            axis = self.determine_axis_for_prefix(prefix_or_tag) if prefix_or_tag.endswith('_') else None
            self.insert_color(prefix_or_tag, color, axis)

    def run(self):
        """Run the full migration."""
        print("=" * 60)
        print("Mail Classifier v3.0 - Rules Migration")
        print("=" * 60)
        print(f"Database: {self.db_path}")
        print(f"Config dir: {self.config_dir}")
        print()

        self.connect()
        self.run_schema_migration()

        print("\nMigrating rules files:")
        for filename, axes in self.FILES_CONFIG.items():
            self.migrate_file(filename, axes)

        self.conn.commit()

        # Print summary
        print("\n" + "=" * 60)
        print("Migration Summary")
        print("=" * 60)
        print(f"  Tags migrated:            {self.stats['tags']}")
        print(f"  Constraints migrated:     {self.stats['constraints']}")
        print(f"  Inference rules migrated: {self.stats['inference_rules']}")
        print(f"  Definitions migrated:     {self.stats['definitions']}")
        print(f"  Colors migrated:          {self.stats['colors']}")

        if self.stats['errors']:
            print(f"\n  Errors: {len(self.stats['errors'])}")
            for error in self.stats['errors'][:10]:
                print(f"    - {error}")
            if len(self.stats['errors']) > 10:
                print(f"    ... and {len(self.stats['errors']) - 10} more")

        self.close()
        print("\nMigration complete!")
        return len(self.stats['errors']) == 0


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Migrate rules to database')
    parser.add_argument('--db-path', default='mail_classifier.db',
                        help='Path to SQLite database')
    parser.add_argument('--config-dir', default='config',
                        help='Path to config directory with rules files')

    args = parser.parse_args()

    # Resolve paths relative to project root
    project_root = Path(__file__).parent.parent
    db_path = project_root / args.db_path
    config_dir = project_root / args.config_dir

    migrator = RulesMigrator(str(db_path), str(config_dir))
    success = migrator.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
