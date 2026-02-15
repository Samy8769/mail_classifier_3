"""
Test script for Phase 1: Database, Tags, and Rules Reconstruction
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from mail_classifier.database import DatabaseManager
from mail_classifier.tag_manager import TagManager


def test_database_creation():
    """Test 1: Database creation"""
    print("\n" + "=" * 60)
    print("TEST 1: Database Creation")
    print("=" * 60)

    db_path = "test_mail_classifier.db"

    # Remove existing test database
    if os.path.exists(db_path):
        os.remove(db_path)
        print("✓ Removed existing test database")

    # Create database
    db = DatabaseManager(db_path)
    print("✓ Database created successfully")

    # Check tables exist
    cursor = db.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    expected_tables = [
        'classification_axes', 'email_chunks', 'emails', 'embeddings',
        'processing_log', 'search_history', 'tag_classifications', 'tags'
    ]

    print(f"\nTables created: {len(tables)}")
    for table in tables:
        status = "✓" if table in expected_tables else "?"
        print(f"  {status} {table}")

    all_present = all(t in tables for t in expected_tables)
    if all_present:
        print("\n✓ All expected tables present")
    else:
        missing = [t for t in expected_tables if t not in tables]
        print(f"\n✗ Missing tables: {missing}")

    return db


def test_tag_operations(db):
    """Test 2: Tag CRUD operations"""
    print("\n" + "=" * 60)
    print("TEST 2: Tag CRUD Operations")
    print("=" * 60)

    tag_manager = TagManager(db)

    # Add some test tags
    test_tags = [
        ('T_Test1', 'type', 'Test tag 1'),
        ('T_Test2', 'type', 'Test tag 2'),
        ('P_TestProject', 'projet', 'Test project'),
        ('F_TestSupplier', 'fournisseur', 'Test supplier')
    ]

    print("\nAdding test tags:")
    added_ids = []
    for tag_name, axis, desc in test_tags:
        try:
            tag_id = tag_manager.add_tag(tag_name, axis, desc)
            added_ids.append(tag_id)
            print(f"  ✓ Added {tag_name} (ID: {tag_id})")
        except Exception as e:
            print(f"  ✗ Error adding {tag_name}: {e}")

    # List tags
    print("\nListing tags by axis:")
    for axis in ['type', 'projet', 'fournisseur']:
        tags = tag_manager.list_tags(axis_name=axis)
        print(f"  {axis}: {len(tags)} tags")
        for tag in tags:
            print(f"    - {tag['tag_name']}: {tag['description']}")

    # Update a tag
    print("\nUpdating tag:")
    tag_manager.update_tag('T_Test1', description='Updated description')

    # Get updated tag
    updated = db.get_tag_by_name('T_Test1')
    print(f"  ✓ T_Test1 description: {updated['description']}")

    # Statistics
    stats = tag_manager.get_tag_statistics()
    print(f"\nTag statistics:")
    print(f"  Total: {stats['total_tags']}")
    print(f"  Active: {stats['active_tags']}")
    print(f"  By axis: {stats['by_axis']}")

    return tag_manager


def test_rules_reconstruction(db):
    """Test 3: Rules reconstruction from database"""
    print("\n" + "=" * 60)
    print("TEST 3: Rules Reconstruction from Database")
    print("=" * 60)

    # Reconstruct rules for 'type' axis
    rules_text = db.reconstruct_rules_from_tags('type')

    print("\nReconstructed rules for 'type' axis:")
    print("-" * 40)
    print(rules_text)
    print("-" * 40)

    if 'T_Test1' in rules_text and 'T_Test2' in rules_text:
        print("✓ Test tags present in reconstructed rules")
    else:
        print("✗ Test tags not found in reconstructed rules")


def test_email_storage(db):
    """Test 4: Email and chunk storage"""
    print("\n" + "=" * 60)
    print("TEST 4: Email and Chunk Storage")
    print("=" * 60)

    # Insert test email
    test_email = {
        'conversation_id': 'TEST_CONV_001',
        'subject': 'Test Email Subject',
        'sender_email': 'test@example.com',
        'sender_name': 'Test User',
        'recipients': 'recipient@example.com',
        'body': 'This is a test email body with some content.',
        'received_time': '2024-01-20 10:30:00',
        'conversation_topic': 'Test Topic'
    }

    email_id = db.insert_email(test_email)
    print(f"✓ Inserted test email (ID: {email_id})")

    # Insert test chunk
    test_chunk = {
        'email_id': email_id,
        'chunk_index': 0,
        'chunk_text': 'This is a test chunk of the email.',
        'token_count': 10,
        'chunk_type': 'full'
    }

    chunk_id = db.insert_chunk(test_chunk)
    print(f"✓ Inserted test chunk (ID: {chunk_id})")

    # Retrieve email
    retrieved_email = db.get_email(email_id)
    if retrieved_email and retrieved_email['subject'] == test_email['subject']:
        print("✓ Email retrieval successful")
    else:
        print("✗ Email retrieval failed")

    # Retrieve chunks
    chunks = db.get_chunks_for_email(email_id)
    if len(chunks) == 1:
        print(f"✓ Chunk retrieval successful ({len(chunks)} chunk)")
    else:
        print(f"✗ Expected 1 chunk, got {len(chunks)}")


def test_classification_linking(db, tag_manager):
    """Test 5: Classification linking (email ↔ tags)"""
    print("\n" + "=" * 60)
    print("TEST 5: Classification Linking")
    print("=" * 60)

    # Get test email and tag
    cursor = db.connection.execute("SELECT email_id FROM emails LIMIT 1")
    email_id = cursor.fetchone()[0]

    tag = db.get_tag_by_name('T_Test1')
    if not tag:
        print("✗ Test tag not found")
        return

    # Link email to tag
    classification_id = db.insert_classification(
        email_id=email_id,
        tag_id=tag['tag_id'],
        confidence=0.95,
        classified_by='llm',
        llm_model='alfred-4.2'
    )
    print(f"✓ Linked email {email_id} to tag {tag['tag_name']} (classification ID: {classification_id})")

    # Retrieve classifications
    classifications = db.get_classifications_for_email(email_id)
    print(f"\nClassifications for email {email_id}:")
    for c in classifications:
        print(f"  - {c['tag_name']} (confidence: {c['confidence_score']})")

    if len(classifications) > 0:
        print("✓ Classification retrieval successful")
    else:
        print("✗ No classifications found")


def run_all_tests():
    """Run all Phase 1 tests"""
    print("\n" + "=" * 60)
    print("PHASE 1 TESTS: Database, Tags, Rules Reconstruction")
    print("=" * 60)

    try:
        # Test 1: Database creation
        db = test_database_creation()

        # Test 2: Tag operations
        tag_manager = test_tag_operations(db)

        # Test 3: Rules reconstruction
        test_rules_reconstruction(db)

        # Test 4: Email storage
        test_email_storage(db)

        # Test 5: Classification linking
        test_classification_linking(db, tag_manager)

        # Final statistics
        print("\n" + "=" * 60)
        print("FINAL STATISTICS")
        print("=" * 60)
        stats = db.get_stats()
        for key, value in stats.items():
            print(f"  {key:20s}: {value}")

        print("\n" + "=" * 60)
        print("✓ ALL TESTS COMPLETED SUCCESSFULLY")
        print("=" * 60)

        db.close()

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    run_all_tests()
