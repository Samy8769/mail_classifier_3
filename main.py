"""
Main entry point for mail_classifier CLI v2.0.
Orchestrates all components and provides enhanced command-line interface.

Features:
- Email classification (original functionality)
- Semantic search
- Tag management
- Database operations
"""

import argparse
import sys

# Core components (v1.0)
from mail_classifier.config import Config, ConfigError
from mail_classifier.email_client import EmailClient
from mail_classifier.categorizer import Categorizer
from mail_classifier.api_client import ParadigmAPIClient, APIError
from mail_classifier.state_manager import StateManager

# Enhanced components (v2.0)
from mail_classifier.database import DatabaseManager
from mail_classifier.chunker import EmailChunker
from mail_classifier.tag_manager import TagManager
from mail_classifier.validator import TagValidator
from mail_classifier.vector_store import VectorStore
from mail_classifier.search_engine import SearchEngine
from mail_classifier.banner import display_banner, display_help, display_short_help
from mail_classifier import cli_commands


def create_parser():
    """Create argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        description='Mail Classifier v2.0 - AI-Powered Email Classification & Search',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False
    )

    parser.add_argument(
        '--config',
        default='config/settings.json',
        help='Path to configuration file (default: config/settings.json)'
    )

    parser.add_argument(
        '--help', '-h',
        action='store_true',
        help='Show this help message'
    )

    parser.add_argument(
        '--version',
        action='store_true',
        help='Show version information'
    )

    # Create subcommands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # ===== CLASSIFY COMMAND =====
    classify_parser = subparsers.add_parser(
        'classify',
        help='Classify emails using AI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py classify
  python main.py classify --folder "Sent Items"
  python main.py classify --dry-run --verbose
        """
    )
    classify_parser.add_argument(
        '--folder',
        help='Outlook folder to process (name or number: 6=Inbox, 5=Sent)'
    )
    classify_parser.add_argument(
        '--clear-cache',
        action='store_true',
        help='Clear conversation cache before processing'
    )
    classify_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Process emails but do not apply categories'
    )
    classify_parser.add_argument(
        '--no-validation',
        action='store_true',
        help='Disable LLM validation of tags'
    )
    classify_parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    # ===== SEARCH COMMAND =====
    search_parser = subparsers.add_parser(
        'search',
        help='Semantic search in classified emails',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py search "anomalies tests satellite"
  python main.py search "projet YODA" --top-k 5
  python main.py search "fournisseur optique" --interactive
        """
    )
    search_parser.add_argument(
        'query',
        help='Search query (semantic search)'
    )
    search_parser.add_argument(
        '--top-k',
        type=int,
        default=10,
        help='Number of results to return (default: 10)'
    )
    search_parser.add_argument(
        '--interactive',
        action='store_true',
        help='Interactive mode to view full emails'
    )
    search_parser.add_argument(
        '--min-score',
        type=float,
        default=0.0,
        help='Minimum similarity score (0.0-1.0, default: 0.0)'
    )

    # ===== ADD-TAG COMMAND =====
    add_tag_parser = subparsers.add_parser(
        'add-tag',
        help='Add a new classification tag',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py add-tag T_Cybersecurite type --description "Sujets cybersécurité"
  python main.py add-tag P_JWST projet --description "Projet James Webb"
        """
    )
    add_tag_parser.add_argument(
        'tag_name',
        help='Tag name (e.g., T_NewType, P_NewProject)'
    )
    add_tag_parser.add_argument(
        'axis',
        nargs='?',
        help='Classification axis (type, projet, fournisseur, etc.) - auto-detected if omitted'
    )
    add_tag_parser.add_argument(
        '--description',
        help='Tag description'
    )

    # ===== LIST-TAGS COMMAND =====
    list_tags_parser = subparsers.add_parser(
        'list-tags',
        help='List classification tags',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py list-tags
  python main.py list-tags --axis type
  python main.py list-tags --prefix P_
        """
    )
    list_tags_parser.add_argument(
        '--axis',
        help='Filter by classification axis'
    )
    list_tags_parser.add_argument(
        '--prefix',
        help='Filter by tag prefix (T_, P_, F_, etc.)'
    )
    list_tags_parser.add_argument(
        '--show-inactive',
        action='store_true',
        help='Include inactive tags'
    )

    # ===== UPDATE-TAG COMMAND =====
    update_tag_parser = subparsers.add_parser(
        'update-tag',
        help='Update an existing tag',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py update-tag T_OldType --description "Updated description"
  python main.py update-tag T_Obsolete --deactivate
        """
    )
    update_tag_parser.add_argument(
        'tag_name',
        help='Tag name to update'
    )
    update_tag_parser.add_argument(
        '--description',
        help='New description'
    )
    update_tag_parser.add_argument(
        '--deactivate',
        action='store_true',
        help='Deactivate the tag'
    )

    # ===== DELETE-TAG COMMAND =====
    delete_tag_parser = subparsers.add_parser(
        'delete-tag',
        help='Delete a tag (soft delete by default)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py delete-tag T_OldType
  python main.py delete-tag T_Temp --hard  # Permanent deletion
        """
    )
    delete_tag_parser.add_argument(
        'tag_name',
        help='Tag name to delete'
    )
    delete_tag_parser.add_argument(
        '--hard',
        action='store_true',
        help='Permanent deletion (cannot be undone)'
    )

    # ===== DB-STATUS COMMAND =====
    subparsers.add_parser(
        'db-status',
        help='Show database statistics'
    )

    # ===== DB-MIGRATE COMMAND =====
    subparsers.add_parser(
        'db-migrate',
        help='Run database migrations'
    )

    # ===== EMBED-ALL COMMAND =====
    embed_parser = subparsers.add_parser(
        'embed-all',
        help='Generate embeddings for all emails',
        epilog="""
Examples:
  python main.py embed-all
  python main.py embed-all --background
        """
    )
    embed_parser.add_argument(
        '--background',
        action='store_true',
        help='Run in background (not yet implemented)'
    )

    # ===== HELP COMMAND =====
    subparsers.add_parser(
        'help',
        help='Show detailed help'
    )

    return parser


def initialize_v2_components(config):
    """
    Initialize v2.0 components based on configuration.

    Returns:
        Tuple of (db, chunker, tag_manager, validator, vector_store, search_engine)
    """
    db = None
    chunker = None
    tag_manager = None
    validator = None
    vector_store = None
    search_engine = None
 
    # Database
    if config.database.get('enabled', False):

        db = DatabaseManager(db_path=config.database.get('db_path', 'mail_classifier.db'))

        tag_manager = TagManager(db)
        
    # Chunker
    if config.chunking.get('enabled', False):
        chunker = EmailChunker(
            max_tokens=config.chunking.get('max_tokens', 32000),
            overlap_tokens=config.chunking.get('overlap_tokens', 200)
        )

    # API client for embeddings and validation
    if config.validation.get('enabled', True) or config.embeddings.get('enabled', False):
        api_client = ParadigmAPIClient(config.api, config.proxy)
        
        # Validator
        if config.validation.get('enabled', True) and db:
            validator = TagValidator(config,db, api_client)

        # Vector store and search
        if config.embeddings.get('enabled', False) and db:
            vector_store = VectorStore(
                db,
                api_client,
                storage_dir=config.embeddings.get('storage_dir', 'embeddings'),
                embedding_model=config.embeddings.get('model', 'multilingual-e5-large'),
                embedding_dim=config.embeddings.get('dimension', 1024)
            )
            search_engine = SearchEngine(vector_store, db)

    return db, chunker, tag_manager, validator, vector_store, search_engine


def cmd_classify(args, config):
    """Handle classify command."""
    try:
        # Apply CLI overrides
        if args.folder:
            try:
                folder_spec = int(args.folder)
            except ValueError:
                folder_spec = args.folder
            config.outlook['default_folders'] = [folder_spec]

        # Initialize v1.0 components
        print("Initializing components...")
        api_client = ParadigmAPIClient(config.api, config.proxy)
        state_manager = StateManager(config.state, config.outlook)
        email_client = EmailClient(config.outlook)

        # Initialize v2.0 components
        db, chunker, _, validator, vector_store, _ = initialize_v2_components(config)

        # Override validation if --no-validation flag
        if args.no_validation:
            validator = None

        # Initialize categorizer with v2.0 components
        categorizer = Categorizer(
            config,
            api_client,
            state_manager,
            db=db,
            chunker=chunker,
            validator=validator,
            vector_store=vector_store
        )
        print("Components initialized.")

        # Clear cache if requested
        if args.clear_cache:
            state_manager.clear_cache()

        # Process each configured folder
        for folder_spec in config.outlook['default_folders']:
            process_folder(
                email_client,
                categorizer,
                state_manager,
                folder_spec,
                dry_run=args.dry_run,
                verbose=args.verbose
            )

        print("\n✅ Processing complete!")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def process_folder(email_client: EmailClient, categorizer: Categorizer,
                   state_manager: StateManager, folder_spec,
                   dry_run: bool = False, verbose: bool = False):
    """
    Main processing logic for a single folder.

    Args:
        email_client: EmailClient instance
        categorizer: Categorizer instance
        state_manager: StateManager instance
        folder_spec: Folder name or number
        dry_run: If True, don't apply categories
        verbose: If True, print verbose output
    """
    print(f"\n{'='*60}")
    print(f"Processing folder: {folder_spec}")
    print(f"{'='*60}")

    try:
        # Get folder
        folder = email_client.get_folder_by_name_or_number(folder_spec)
        print(f"Folder found: {folder.Name}")

        # Get emails with AI category, excluding AI done
        print(f"\nSearching for emails with category '{email_client.ai_category}'...")
        emails = email_client.get_emails_by_category(
            folder,
            category=email_client.ai_category,
            exclude_category=email_client.done_category
        )

        if not emails:
            print("No emails to process.")
            return

        print(f"Found {len(emails)} emails to process")

        # Group by conversation
        conversations = email_client.group_by_conversation(emails)
        print(f"Grouped into {len(conversations)} conversations")

        # Process each conversation
        processed_count = 0
        skipped_count = 0

        for conv_id, conv_emails in conversations.items():
            try:
                print(f"\n--- Conversation {processed_count + skipped_count + 1}/{len(conversations)} ---")
                if verbose:
                    print(f"Conversation ID: {conv_id}")
                    print(f"Emails in conversation: {len(conv_emails)}")

                # Smart processing: skip if already done
                if state_manager.verify_with_outlook(email_client, folder, conv_id):
                    print(f"Conversation already processed, skipping")
                    skipped_count += 1
                    continue

                print(f"Processing conversation with {len(conv_emails)} emails...")

                # Categorize (with v2.0 features: chunking, validation, DB storage)
                categories = categorizer.categorize_conversation(conv_id, conv_emails)

                if verbose:
                    print(f"Categories found: {categories}")
                else:
                    print(f"Categories: {', '.join(categories)}")

                # Apply categories (unless dry run)
                if not dry_run:
                    email_client.apply_categories_to_conversation(
                        folder,
                        conv_id,
                        categories
                    )
                    processed_count += 1
                else:
                    print("DRY RUN: Categories not applied")
                    processed_count += 1

            except APIError as e:
                print(f"API error processing conversation: {e}")
                continue
            except Exception as e:
                print(f"Error processing conversation: {e}")
                if verbose:
                    import traceback
                    traceback.print_exc()
                continue

        # Summary
        print(f"\n{'='*60}")
        print(f"Folder processing complete:")
        print(f"  - Processed: {processed_count} conversations")
        print(f"  - Skipped: {skipped_count} conversations")
        print(f"  - Total: {len(conversations)} conversations")
        print(f"{'='*60}")

    except ValueError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Error processing folder: {e}")
        if verbose:
            import traceback
            traceback.print_exc()


def main():
    """Main entry point with subcommand routing."""
    parser = create_parser()
    args = parser.parse_args()

    # Handle special flags
    if args.version:
        print("Mail Classifier v2.0")
        print("Enhanced with semantic search, chunking, and database features")
        sys.exit(0)

    if args.help or args.command is None:
        if args.command == 'help':
            display_help()
        elif args.help:
            display_short_help()
        else:
            # No command specified - show banner
            display_banner()
        sys.exit(0)

    # Load configuration
    try:
        config = Config.load(args.config)
    except ConfigError as e:
        print(f"❌ Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    # Route to appropriate command handler
    try:
        if args.command == 'classify':
            cmd_classify(args, config)

        elif args.command == 'search':
            # Initialize search components
            db, _, _, _, vector_store, search_engine = initialize_v2_components(config)
            if not search_engine:
                print("❌ Error: Embeddings must be enabled for search")
                print("Set 'embeddings.enabled: true' in config/settings.json")
                sys.exit(1)
            cli_commands.cmd_search(args, search_engine)

        elif args.command == 'add-tag':
            db, _, tag_manager, _, _, _ = initialize_v2_components(config)
            if not tag_manager:
                print("❌ Error: Database must be enabled for tag management")
                sys.exit(1)
            cli_commands.cmd_add_tag(args, tag_manager)

        elif args.command == 'list-tags':
            db, _, tag_manager, _, _, _ = initialize_v2_components(config)
            if not tag_manager:
                print("❌ Error: Database must be enabled for tag management")
                sys.exit(1)
            cli_commands.cmd_list_tags(args, tag_manager)

        elif args.command == 'update-tag':
            db, _, tag_manager, _, _, _ = initialize_v2_components(config)
            if not tag_manager:
                print("❌ Error: Database must be enabled for tag management")
                sys.exit(1)
            cli_commands.cmd_update_tag(args, tag_manager)

        elif args.command == 'delete-tag':
            db, _, tag_manager, _, _, _ = initialize_v2_components(config)
            if not tag_manager:
                print("❌ Error: Database must be enabled for tag management")
                sys.exit(1)
            cli_commands.cmd_delete_tag(args, tag_manager)

        elif args.command == 'db-status':
            db, _, _, _, _, _ = initialize_v2_components(config)
            if not db:
                print("❌ Error: Database must be enabled")
                sys.exit(1)
            cli_commands.cmd_db_status(db)

        elif args.command == 'db-migrate':
            db, _, _, _, _, _ = initialize_v2_components(config)
            if not db:
                print("❌ Error: Database must be enabled")
                sys.exit(1)
            cli_commands.cmd_db_migrate(db)

        elif args.command == 'embed-all':
            db, _, _, _, vector_store, _ = initialize_v2_components(config)
            if not vector_store:
                print("❌ Error: Embeddings must be enabled")
                sys.exit(1)
            cli_commands.cmd_embed_all(args, vector_store, db)

        else:
            print(f"❌ Unknown command: {args.command}")
            display_short_help()
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal error: {e}", file=sys.stderr)
        if hasattr(args, 'verbose') and args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
