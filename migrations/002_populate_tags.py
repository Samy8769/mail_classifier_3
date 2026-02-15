"""
Migrate tags from regles_mail_*.txt files to database.
Extracts tags from YAML format and populates tags table.
"""

import sys
import os
import re

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mail_classifier.database import DatabaseManager
from mail_classifier.tag_manager import TagManager


def parse_rules_file_simple(filepath: str, axis_name: str) -> list:
    """
    Parse YAML rules file into tag dictionaries.
    Simple parser that extracts tag names from YAML structure.

    Args:
        filepath: Path to regles_mail_*.txt file
        axis_name: Classification axis name

    Returns:
        List of tag dictionaries
    """
    if not os.path.exists(filepath):
        print(f"⚠ File not found: {filepath}")
        return []

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    tags = []

    # Extract tags using regex patterns
    # Pattern 1: Direct tag names (e.g., "T_Client", "P_YODA_CL")
    # Looking for lines with tag patterns like: "T_", "P_", "F_", "E_", "Proc_", "S_", "A_", "C_"
    patterns = [
        r'([TPFESC]_[A-Za-z0-9_-]+)',  # T_, P_, F_, E_, S_, C_
        r'(Proc_[A-Za-z0-9_-]+)',       # Proc_
        r'(A_[A-Za-z0-9_\s-]+)',        # A_ (Affairs)
    ]

    for pattern in patterns:
        matches = re.findall(pattern, content)
        for match in matches:
            tag_name = match.strip()
            # Avoid duplicates
            if not any(t['tag_name'] == tag_name for t in tags):
                # Determine prefix
                if '_' in tag_name:
                    prefix = tag_name.split('_')[0] + '_'
                else:
                    prefix = tag_name[0] + '_'

                tags.append({
                    'tag_name': tag_name,
                    'axis_name': axis_name,
                    'prefix': prefix,
                    'description': None
                })

    return tags


def migrate_tags_from_files(db_path: str = None):
    """
    Main migration function.

    Args:
        db_path: Optional database path (uses default if None)
    """
    print("=" * 60)
    print("Tag Migration: regles_mail_*.txt → Database")
    print("=" * 60)

    # Initialize database and tag manager
    db = DatabaseManager(db_path) if db_path else DatabaseManager()
    tag_manager = TagManager(db)

    # Define rules files mapping
    config_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'config'
    )

    rules_files = {
        'type': os.path.join(config_dir, 'regles_mail_type.txt'),
        'projet': os.path.join(config_dir, 'regles_mail_projet.txt'),
        'fournisseur': os.path.join(config_dir, 'regles_mail_fournisseur.txt'),
        'equipement': os.path.join(config_dir, 'regles_mail_equipement.txt'),
        'processus': os.path.join(config_dir, 'regles_mail_processus.txt')
    }

    total_imported = 0
    total_skipped = 0

    for axis_name, filepath in rules_files.items():
        print(f"\n📂 Processing axis: {axis_name}")
        print(f"   File: {filepath}")

        if not os.path.exists(filepath):
            print(f"   ⚠ File not found, skipping")
            continue

        # Parse tags from file
        tags = parse_rules_file_simple(filepath, axis_name)
        print(f"   Found {len(tags)} tags")

        # Insert tags
        imported = 0
        skipped = 0

        for tag_data in tags:
            try:
                tag_manager.add_tag(
                    tag_name=tag_data['tag_name'],
                    axis_name=tag_data['axis_name'],
                    description=tag_data.get('description')
                )
                imported += 1
            except ValueError as e:
                # Tag already exists or other validation error
                skipped += 1
            except Exception as e:
                print(f"   ✗ Error importing {tag_data['tag_name']}: {e}")
                skipped += 1

        print(f"   ✓ Imported: {imported}, Skipped: {skipped}")
        total_imported += imported
        total_skipped += skipped

    print("\n" + "=" * 60)
    print("Migration Summary:")
    print(f"  Total imported: {total_imported}")
    print(f"  Total skipped:  {total_skipped}")
    print("=" * 60)

    # Show statistics
    stats = tag_manager.get_tag_statistics()
    print("\nDatabase Statistics:")
    print(f"  Active tags:   {stats['active_tags']}")
    print(f"  Inactive tags: {stats['inactive_tags']}")
    print(f"\nBy Axis:")
    for axis, counts in stats['by_axis'].items():
        print(f"  {axis:15s}: {counts['active']} active")

    db.close()
    print("\n✓ Migration complete!")


if __name__ == '__main__':
    migrate_tags_from_files()
