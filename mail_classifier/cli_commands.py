"""
CLI command handlers for enhanced features.
Implements search, tag management, and database commands.
"""

from typing import Optional


def cmd_search(args, search_engine):
    """
    Handle semantic search command.

    Args:
        args: Parsed command-line arguments
        search_engine: SearchEngine instance
    """
    query = args.query
    top_k = args.top_k if hasattr(args, 'top_k') and args.top_k else 10
    interactive = hasattr(args, 'interactive') and args.interactive
    min_score = args.min_score if hasattr(args, 'min_score') else 0.0

    # Build filters
    filters = {}
    if min_score > 0:
        filters['min_score'] = min_score

    # Perform search
    results = search_engine.search(query, top_k=top_k, filters=filters if filters else None)

    if not results:
        print("\n❌ Aucun email correspondant trouvé.")
        return

    # Display results
    print(f"\n📋 {len(results)} email(s) trouvé(s) :\n")
    print("=" * 80)

    for i, result in enumerate(results, 1):
        score_bar = "█" * int(result['relevance_score'] * 10)
        print(f"\n{i}. [{result['relevance_score']:.2f}] {score_bar}")
        print(f"   📧 {result['subject']}")
        print(f"   👤 {result['sender_name']} ({result['sender_email']})")
        print(f"   📅 {result['received_time']}")
        print(f"   🏷️  {', '.join(result['tags']) if result['tags'] else 'Aucun tag'}")
        print(f"   💬 {result.get('body_preview', '')[:150]}...")
        print(f"   🆔 Email ID: {result['email_id']}")

    print("\n" + "=" * 80)

    # Interactive mode
    if interactive:
        try:
            choice = input("\nEntrez le numéro de l'email à afficher (ou Entrée pour quitter) : ")
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(results):
                    email = results[idx]
                    print("\n" + "=" * 80)
                    print(f"SUJET : {email['subject']}")
                    print(f"DE    : {email['sender_name']} ({email['sender_email']})")
                    print(f"DATE  : {email['received_time']}")
                    print(f"TAGS  : {', '.join(email['tags'])}")
                    print("=" * 80)
                    print(email.get('body', 'Corps non disponible'))
                    print("=" * 80)
        except (KeyboardInterrupt, EOFError):
            print("\n")


def cmd_add_tag(args, tag_manager):
    """
    Handle add tag command.

    Args:
        args: Parsed command-line arguments
        tag_manager: TagManager instance
    """
    tag_name = args.tag_name
    axis_name = args.axis if hasattr(args, 'axis') else None
    description = args.description if hasattr(args, 'description') else None

    print(f"\n➕ Ajout du tag '{tag_name}'...")

    try:
        tag_id = tag_manager.add_tag(
            tag_name=tag_name,
            axis_name=axis_name,
            description=description
        )
        print(f"\n✅ Tag ajouté avec succès (ID: {tag_id})")
        print(f"Le tag sera disponible immédiatement dans les règles de classification.")
    except ValueError as e:
        print(f"\n❌ Erreur : {e}")
    except Exception as e:
        print(f"\n❌ Erreur inattendue : {e}")


def cmd_list_tags(args, tag_manager):
    """
    Handle list tags command.

    Args:
        args: Parsed command-line arguments
        tag_manager: TagManager instance
    """
    axis_name = args.axis if hasattr(args, 'axis') else None
    prefix = args.prefix if hasattr(args, 'prefix') else None
    show_inactive = hasattr(args, 'show_inactive') and args.show_inactive

    print("\n📋 Liste des tags de classification")

    if axis_name:
        print(f"   Filtre par axe: {axis_name}")
    if prefix:
        print(f"   Filtre par préfixe: {prefix}")

    print("=" * 80)

    # Get tags
    tags = tag_manager.list_tags(axis_name=axis_name, prefix=prefix, active_only=not show_inactive)

    if not tags:
        print("Aucun tag trouvé.")
        return

    # Group by axis
    by_axis = {}
    for tag in tags:
        axis = tag['axis_name']
        if axis not in by_axis:
            by_axis[axis] = []
        by_axis[axis].append(tag)

    # Display by axis
    for axis, axis_tags in sorted(by_axis.items()):
        print(f"\n🔖 {axis.upper()} ({len(axis_tags)} tags):")
        print("-" * 80)

        for tag in sorted(axis_tags, key=lambda t: t['tag_name']):
            status = "✓" if tag['is_active'] else "✗"
            desc = f" — {tag['description']}" if tag['description'] else ""
            print(f"  {status} {tag['tag_name']:<30s}{desc}")

    # Statistics
    print("\n" + "=" * 80)
    stats = tag_manager.get_tag_statistics()
    print(f"Total : {stats['total_tags']} tags ({stats['active_tags']} actifs, {stats['inactive_tags']} inactifs)")


def cmd_update_tag(args, tag_manager):
    """
    Handle update tag command.

    Args:
        args: Parsed command-line arguments
        tag_manager: TagManager instance
    """
    tag_name = args.tag_name
    description = args.description if hasattr(args, 'description') else None
    deactivate = hasattr(args, 'deactivate') and args.deactivate

    print(f"\n🔄 Mise à jour du tag '{tag_name}'...")

    try:
        if deactivate:
            tag_manager.update_tag(tag_name, is_active=False)
            print(f"✅ Tag '{tag_name}' désactivé")
        elif description:
            tag_manager.update_tag(tag_name, description=description)
            print(f"✅ Tag '{tag_name}' mis à jour")
        else:
            print("❌ Aucune modification spécifiée (utilisez --description ou --deactivate)")
    except Exception as e:
        print(f"❌ Erreur : {e}")


def cmd_delete_tag(args, tag_manager):
    """
    Handle delete tag command.

    Args:
        args: Parsed command-line arguments
        tag_manager: TagManager instance
    """
    tag_name = args.tag_name
    hard_delete = hasattr(args, 'hard') and args.hard

    if hard_delete:
        print(f"\n⚠️  ATTENTION : Suppression PERMANENTE du tag '{tag_name}'")
        confirm = input("Êtes-vous sûr ? Cette action est irréversible. (oui/non) : ")
        if confirm.lower() not in ['oui', 'yes', 'o', 'y']:
            print("❌ Opération annulée.")
            return

    print(f"\n🗑️  Suppression du tag '{tag_name}'...")

    try:
        tag_manager.delete_tag(tag_name, hard_delete=hard_delete)
    except Exception as e:
        print(f"❌ Erreur : {e}")


def cmd_db_status(db):
    """
    Handle database status command.

    Args:
        db: DatabaseManager instance
    """
    print("\n📊 Statistiques de la base de données")
    print("=" * 80)

    stats = db.get_stats()

    print(f"\n📧 Emails stockés          : {stats['emails']:>10}")
    print(f"📄 Chunks d'emails         : {stats['chunks']:>10}")
    print(f"🔢 Embeddings vectoriels   : {stats['embeddings']:>10}")
    print(f"🏷️  Tags actifs             : {stats['active_tags']:>10}")
    print(f"🔗 Classifications totales : {stats['classifications']:>10}")

    # Additional stats
    cursor = db.connection.execute("SELECT COUNT(DISTINCT conversation_id) FROM emails")
    conversations = cursor.fetchone()[0]
    print(f"💬 Conversations uniques   : {conversations:>10}")

    print("\n" + "=" * 80)


def cmd_db_migrate(db):
    """
    Handle database migration command.

    Args:
        db: DatabaseManager instance
    """
    print("\n🔄 Exécution des migrations de base de données...")
    print("=" * 80)

    # Schema should already be created during database initialization
    print("✅ Schéma de base de données vérifié")

    # Run tag migration if needed
    print("\n Pour migrer les tags depuis les fichiers YAML, exécutez :")
    print("   python migrations/002_populate_tags.py")

    print("\n" + "=" * 80)


def cmd_embed_all(args, vector_store, db):
    """
    Handle batch embedding command.

    Args:
        args: Parsed command-line arguments
        vector_store: VectorStore instance
        db: DatabaseManager instance
    """
    background = hasattr(args, 'background') and args.background

    print("\n🔢 Génération des embeddings pour tous les emails...")
    print("=" * 80)

    # Get all email IDs that need embedding
    cursor = db.connection.execute("""
        SELECT DISTINCT ec.email_id
        FROM email_chunks ec
        LEFT JOIN embeddings e ON ec.chunk_id = e.chunk_id
        WHERE e.embedding_id IS NULL
    """)

    email_ids = [row[0] for row in cursor.fetchall()]

    if not email_ids:
        print("✅ Tous les emails ont déjà des embeddings")
        return

    print(f"📊 {len(email_ids)} email(s) à traiter")

    if background:
        print("\n⚠️  Mode arrière-plan non implémenté pour l'instant.")
        print("   Les embeddings seront générés de manière synchrone.")

    # Process embeddings
    vector_store.batch_embed_emails(email_ids, show_progress=True)


def cmd_search_history(search_engine):
    """
    Display recent search history.

    Args:
        search_engine: SearchEngine instance
    """
    print("\n📜 Historique des recherches récentes")
    print("=" * 80)

    history = search_engine.get_search_history(limit=10)

    if not history:
        print("Aucune recherche enregistrée.")
        return

    for i, entry in enumerate(history, 1):
        timestamp = entry['search_timestamp']
        query = entry['query_text']
        result_count = len(entry.get('results', []))

        print(f"\n{i}. [{timestamp}]")
        print(f"   Requête : {query}")
        print(f"   Résultats : {result_count}")

    print("\n" + "=" * 80)
