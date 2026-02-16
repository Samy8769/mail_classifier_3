#!/usr/bin/env python3
"""
Migration script: Split all combined axes into individual axes.

Updates existing tags in the database:
  - 'type' axis:
    - T_ prefix -> 'type_mail'
    - S_ prefix -> 'statut'
  - 'projet' axis:
    - C_ prefix -> 'client'
    - A_ prefix -> 'affaire'
    - P_ prefix -> 'projet' (unchanged)
  - 'processus' axis:
    - E_ prefix -> 'essais'
    - TC_ prefix -> 'technique'
  - 'qualite'/'jalons'/'anomalies'/'nrb' axes: already split in DB

Also duplicates axis_constraints to new axis names.

Note: Run AFTER 006_split_equipement_axis.py if not already applied.

Usage:
    python migrations/007_split_all_axes.py [--db-path path/to/db]
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime


# Mapping: (old_axis_name, prefix) -> new_axis_name
AXIS_SPLITS = [
    # type axis -> type_mail + statut
    ('type', 'T_', 'type_mail'),
    ('type', 'S_', 'statut'),
    # projet axis -> client + affaire + projet (P_ stays as 'projet')
    ('projet', 'C_', 'client'),
    ('projet', 'A_', 'affaire'),
    # processus axis -> essais + technique
    ('processus', 'E_', 'essais'),
    ('processus', 'TC_', 'technique'),
    # equipement axis (in case 006 was not run)
    ('equipement', 'EQT_', 'equipement_type'),
    ('equipement', 'EQ_', 'equipement_designation'),
]

# Constraints to duplicate from old axis to new axes
CONSTRAINT_SPLITS = {
    'type': ['type_mail', 'statut'],
    'projet': ['client', 'affaire', 'projet'],
    'processus': ['essais', 'technique'],
    'equipement': ['equipement_type', 'equipement_designation'],
}


def migrate(db_path: str):
    """Run the full axis split migration."""
    print("=" * 60)
    print("Migration 007: Split all combined axes")
    print("=" * 60)
    print(f"Database: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        now = datetime.now().isoformat()
        total_updated = 0

        # 1. Split tags by prefix
        print("\n--- Splitting tags ---")
        for old_axis, prefix, new_axis in AXIS_SPLITS:
            cursor = conn.execute(
                "UPDATE tags SET axis_name = ?, updated_at = ? "
                "WHERE axis_name = ? AND prefix = ?",
                (new_axis, now, old_axis, prefix)
            )
            count = cursor.rowcount
            if count > 0:
                print(f"  {old_axis}/{prefix} -> {new_axis}: {count} tags")
                total_updated += count

        # 2. Duplicate constraints to new axes
        print("\n--- Duplicating constraints ---")
        for old_axis, new_axes in CONSTRAINT_SPLITS.items():
            constraints = conn.execute(
                "SELECT constraint_text, constraint_order, is_active "
                "FROM axis_constraints WHERE axis_name = ?",
                (old_axis,)
            ).fetchall()

            if not constraints:
                continue

            for new_axis in new_axes:
                for constraint in constraints:
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
                print(f"  {old_axis} -> {new_axis}: {len(constraints)} constraints")

        # 3. Summary - check for remaining legacy axis names
        print("\n--- Summary ---")
        print(f"  Total tags updated: {total_updated}")

        legacy_axes = ['type', 'projet', 'processus', 'equipement']
        for axis in legacy_axes:
            remaining = conn.execute(
                "SELECT COUNT(*) as cnt FROM tags WHERE axis_name = ?",
                (axis,)
            ).fetchone()['cnt']
            if remaining > 0:
                print(f"  WARNING: {remaining} tags still have axis_name='{axis}'")

        # Show new axis distribution
        print("\n  New axis distribution:")
        cursor = conn.execute(
            "SELECT axis_name, COUNT(*) as cnt FROM tags "
            "WHERE is_active = 1 GROUP BY axis_name ORDER BY axis_name"
        )
        for row in cursor:
            print(f"    {row['axis_name']}: {row['cnt']} tags")

        conn.commit()
        print("\nMigration 007 complete!")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Split all combined axes into individual axes'
    )
    parser.add_argument('--db-path', default='mail_classifier.db',
                        help='Path to SQLite database')

    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    db_path = project_root / args.db_path

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Run the initial migration first.")
        sys.exit(1)

    migrate(str(db_path))


if __name__ == "__main__":
    main()
