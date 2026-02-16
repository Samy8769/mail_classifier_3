#!/usr/bin/env python3
"""
Migration script: Split 'equipement' axis into 'equipement_type' and 'equipement_designation'.

Updates existing tags in the database:
  - EQT_ prefix tags: axis_name 'equipement' -> 'equipement_type'
  - EQ_ prefix tags:  axis_name 'equipement' -> 'equipement_designation'

Also updates axis_constraints entries for the split axes.

Usage:
    python migrations/006_split_equipement_axis.py [--db-path path/to/db]
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime


def migrate(db_path: str):
    """Run the equipement axis split migration."""
    print("=" * 60)
    print("Migration 006: Split equipement axis")
    print("=" * 60)
    print(f"Database: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        now = datetime.now().isoformat()

        # 1. Update tags: EQT_ prefix -> equipement_type
        cursor = conn.execute(
            "UPDATE tags SET axis_name = 'equipement_type', updated_at = ? "
            "WHERE axis_name = 'equipement' AND prefix = 'EQT_'",
            (now,)
        )
        eqt_count = cursor.rowcount
        print(f"  EQT_ tags updated to 'equipement_type': {eqt_count}")

        # 2. Update tags: EQ_ prefix -> equipement_designation
        cursor = conn.execute(
            "UPDATE tags SET axis_name = 'equipement_designation', updated_at = ? "
            "WHERE axis_name = 'equipement' AND prefix = 'EQ_'",
            (now,)
        )
        eq_count = cursor.rowcount
        print(f"  EQ_ tags updated to 'equipement_designation': {eq_count}")

        # 3. Duplicate constraints from 'equipement' to both new axes
        constraints = conn.execute(
            "SELECT constraint_text, constraint_order, is_active "
            "FROM axis_constraints WHERE axis_name = 'equipement'"
        ).fetchall()

        for constraint in constraints:
            for new_axis in ('equipement_type', 'equipement_designation'):
                # Check if already exists
                existing = conn.execute(
                    "SELECT 1 FROM axis_constraints "
                    "WHERE axis_name = ? AND constraint_text = ?",
                    (new_axis, constraint['constraint_text'])
                ).fetchone()
                if not existing:
                    conn.execute(
                        "INSERT INTO axis_constraints "
                        "(axis_name, constraint_text, constraint_order, is_active) "
                        "VALUES (?, ?, ?, ?)",
                        (new_axis, constraint['constraint_text'],
                         constraint['constraint_order'], constraint['is_active'])
                    )

        constraint_count = len(constraints)
        print(f"  Constraints duplicated to new axes: {constraint_count}")

        # 4. Check for any remaining 'equipement' tags
        remaining = conn.execute(
            "SELECT COUNT(*) as cnt FROM tags WHERE axis_name = 'equipement'"
        ).fetchone()['cnt']

        if remaining > 0:
            print(f"  WARNING: {remaining} tags still have axis_name='equipement'")
        else:
            print("  All 'equipement' tags successfully split")

        conn.commit()
        print("\nMigration 006 complete!")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Split equipement axis into equipement_type and equipement_designation'
    )
    parser.add_argument('--db-path', default='mail_classifier.db',
                        help='Path to SQLite database')

    args = parser.parse_args()

    # Resolve path relative to project root
    project_root = Path(__file__).parent.parent
    db_path = project_root / args.db_path

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Run the initial migration first.")
        sys.exit(1)

    migrate(str(db_path))


if __name__ == "__main__":
    main()
