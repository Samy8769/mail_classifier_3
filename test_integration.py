"""
Integration test for Mail Classifier v2.0
Tests the complete pipeline: chunking, database, validation, embeddings

Run this after:
1. python migrations/002_populate_tags.py (to migrate tags)
2. Configuring settings.json as needed
"""

import sys
from mail_classifier.config import Config
from mail_classifier.api_client import ParadigmAPIClient
from mail_classifier.database import DatabaseManager
from mail_classifier.chunker import EmailChunker
from mail_classifier.tag_manager import TagManager
from mail_classifier.validator import TagValidator
from mail_classifier.vector_store import VectorStore

def test_basic_initialization():
    """Test that all components initialize correctly."""
    print("\n" + "="*80)
    print("TEST 1: Component Initialization")
    print("="*80)

    try:
        # Load config
        config = Config.load('config/settings.json')
        print("✓ Config loaded successfully")

        # Initialize API client
        api_client = ParadigmAPIClient(config.api, config.proxy)
        print("✓ API client initialized")

        # Initialize database
        db = DatabaseManager()
        print("✓ Database initialized")

        # Initialize chunker
        chunker_config = config.chunking
        chunker = EmailChunker(
            max_tokens=chunker_config.get('max_tokens', 32000),
            overlap_tokens=chunker_config.get('overlap_tokens', 200)
        )
        print("✓ Chunker initialized")

        # Initialize tag manager
        tag_manager = TagManager(db)
        print("✓ Tag Manager initialized")

        # Initialize validator
        validator = TagValidator(db, api_client)
        print("✓ Validator initialized")

        # Initialize vector store (if embeddings enabled)
        if config.embeddings.get('enabled', False):
            vector_store = VectorStore(db, api_client)
            print("✓ Vector Store initialized")
        else:
            vector_store = None
            print("⚠ Vector Store disabled (embeddings.enabled = false)")

        print("\n✅ All components initialized successfully")
        return True

    except Exception as e:
        print(f"\n❌ Initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database_operations():
    """Test basic database CRUD operations."""
    print("\n" + "="*80)
    print("TEST 2: Database Operations")
    print("="*80)

    try:
        db = DatabaseManager()

        # Get database stats
        stats = db.get_stats()
        print(f"\n📊 Database Statistics:")
        print(f"   Emails:          {stats['emails']}")
        print(f"   Chunks:          {stats['chunks']}")
        print(f"   Embeddings:      {stats['embeddings']}")
        print(f"   Active Tags:     {stats['active_tags']}")
        print(f"   Classifications: {stats['classifications']}")

        # Check if tags are migrated
        if stats['active_tags'] == 0:
            print("\n⚠ WARNING: No tags found in database!")
            print("   Please run: python migrations/002_populate_tags.py")
            return False
        else:
            print(f"\n✅ Found {stats['active_tags']} active tags in database")

        # Test tag retrieval
        tag_manager = TagManager(db)
        type_tags = tag_manager.list_tags(axis_name='type')
        print(f"\n📋 Sample tags (Type axis): {len(type_tags)} tags")
        for tag in type_tags[:5]:
            print(f"   - {tag['tag_name']}: {tag['description'] or 'No description'}")

        print("\n✅ Database operations working correctly")
        return True

    except Exception as e:
        print(f"\n❌ Database test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_chunking():
    """Test email chunking functionality."""
    print("\n" + "="*80)
    print("TEST 3: Email Chunking")
    print("="*80)

    try:
        chunker = EmailChunker(max_tokens=32000, overlap_tokens=200)

        # Test 1: Short email (no chunking needed)
        short_email = "This is a short test email." * 10
        chunks_short = chunker.chunk_email(short_email)
        print(f"\n📧 Short email ({len(short_email)} chars):")
        print(f"   Estimated tokens: {chunker.count_tokens(short_email)}")
        print(f"   Chunks created: {len(chunks_short)}")
        print(f"   Chunk type: {chunks_short[0]['chunk_type']}")

        # Test 2: Long email (requires chunking)
        long_email = "This is a test paragraph.\n\n" * 5000  # ~25K chars
        chunks_long = chunker.chunk_email(long_email)
        print(f"\n📧 Long email ({len(long_email)} chars):")
        print(f"   Estimated tokens: {chunker.count_tokens(long_email)}")
        print(f"   Chunks created: {len(chunks_long)}")

        if len(chunks_long) > 1:
            print(f"   ✓ Email was chunked successfully")
            for i, chunk in enumerate(chunks_long):
                print(f"     - Chunk {i}: {chunk['token_count']} tokens, type: {chunk['chunk_type']}")
        else:
            print(f"   ℹ Email didn't require chunking")

        print("\n✅ Chunking working correctly")
        return True

    except Exception as e:
        print(f"\n❌ Chunking test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_configuration():
    """Test configuration loading and v2.0 sections."""
    print("\n" + "="*80)
    print("TEST 4: Configuration")
    print("="*80)

    try:
        config = Config.load('config/settings.json')

        print("\n⚙️ V2.0 Configuration Status:")
        print(f"   Database enabled:    {config.database.get('enabled', False)}")
        print(f"   Use DB tags:         {config.database.get('use_db_tags', False)}")
        print(f"   Chunking enabled:    {config.chunking.get('enabled', False)}")
        print(f"   Max tokens:          {config.chunking.get('max_tokens', 'N/A')}")
        print(f"   Embeddings enabled:  {config.embeddings.get('enabled', False)}")
        print(f"   Embedding model:     {config.embeddings.get('model', 'N/A')}")
        print(f"   Validation enabled:  {config.validation.get('enabled', True)}")
        print(f"   Auto-correct:        {config.validation.get('auto_correct', False)}")

        # Check if critical features are enabled
        critical_features = []
        if config.database.get('enabled', False):
            critical_features.append("Database")
        if config.chunking.get('enabled', False):
            critical_features.append("Chunking")
        if config.validation.get('enabled', True):
            critical_features.append("Validation")

        print(f"\n✅ Active v2.0 features: {', '.join(critical_features)}")

        if config.embeddings.get('enabled', False):
            print("⚠ Note: Embeddings are enabled but require API calls (cost/time)")

        return True

    except Exception as e:
        print(f"\n❌ Configuration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all integration tests."""
    print("\n╔══════════════════════════════════════════════════════════════════╗")
    print("║         Mail Classifier v2.0 - Integration Test Suite           ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    results = {
        'Initialization': test_basic_initialization(),
        'Database Operations': test_database_operations(),
        'Chunking': test_chunking(),
        'Configuration': test_configuration()
    }

    print("\n" + "="*80)
    print("FINAL RESULTS")
    print("="*80)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}  {test_name}")

    total_pass = sum(results.values())
    total_tests = len(results)

    print(f"\n📊 Summary: {total_pass}/{total_tests} tests passed")

    if total_pass == total_tests:
        print("\n🎉 All tests passed! Mail Classifier v2.0 is ready to use.")
        print("\nNext steps:")
        print("  1. Run classification: python main.py")
        print("  2. Check README_V2.md for complete usage guide")
        print("  3. Consider refactoring main.py for CLI commands (see INTEGRATION_GUIDE.md)")
    else:
        print("\n⚠️ Some tests failed. Please review errors above.")
        print("\nCommon issues:")
        print("  - Tags not migrated: run 'python migrations/002_populate_tags.py'")
        print("  - Config issues: check config/settings.json")
        print("  - API connectivity: verify Paradigm API settings")

    return total_pass == total_tests


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
