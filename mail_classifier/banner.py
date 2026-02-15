"""
Startup banner and help display for CLI.
"""


def display_banner():
    """
    Display welcome banner and feature summary.
    Called at CLI startup.
    """
    banner = """
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║              Mail Classifier - AI-Powered Email Tool             ║
║                       Version 3.1                                ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝

📧 EMAIL CLASSIFICATION
   • Classification multi-axes par IA (Type, Projet, Fournisseur, etc.)
   • Regroupement intelligent des conversations
   • Application automatique de catégories Outlook
   • Gestion emails longs avec chunking intelligent

🔍 RECHERCHE SÉMANTIQUE
   • Recherche par signification, pas seulement mots-clés
   • Recherche vectorielle par similarité
   • Trouve emails pertinents dans tout votre historique

🏷️  GESTION DES TAGS
   • Ajout, modification, suppression de tags de classification
   • Base de données centralisée
   • Génération dynamique des règles pour l'IA

✅ VALIDATION QUALITÉ
   • Vérification conformité des tags par LLM
   • Correction automatique des erreurs
   • Garantit la précision de la classification

📊 FONCTIONNALITÉS AVANCÉES
   • Chunking intelligent pour conversations longues
   • Gestion context window (~32K tokens)
   • Journal complet et historique recherches

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Démarrage rapide :

  Classifier emails :    python main.py classify
  Rechercher emails :    python main.py search "projet YODA mises à jour"
  Ajouter tag :          python main.py add-tag T_NouveauType type
  Lister tags :          python main.py list-tags
  Aide détaillée :       python main.py help

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    print(banner)


def display_help():
    """Display detailed help information."""
    help_text = """
═══════════════════════════════════════════════════════════════════
RÉFÉRENCE COMPLÈTE DES COMMANDES
═══════════════════════════════════════════════════════════════════

COMMANDES DE CLASSIFICATION
─────────────────────────────────────────────────────────────────

  python main.py classify [OPTIONS]

    Traite les emails et applique la classification IA

    Options :
      --folder FOLDER       Dossier Outlook à traiter (défaut: Inbox)
      --dry-run            Prévisualise sans appliquer les catégories
      --clear-cache        Efface le cache des conversations
      --no-validation      Désactive la validation LLM des tags
      --verbose            Affiche des informations détaillées

    Exemples :
      python main.py classify
      python main.py classify --folder "Boîte d'envoi" --verbose
      python main.py classify --dry-run


COMMANDES DE RECHERCHE
─────────────────────────────────────────────────────────────────

  python main.py search "requête" [OPTIONS]

    Recherche sémantique dans tous les emails traités

    Options :
      --top-k N            Nombre de résultats (défaut: 10)
      --interactive        Mode interactif pour ouvrir emails
      --min-score SCORE    Score de similarité minimum (0-1)

    Exemples :
      python main.py search "anomalies tests satellite"
      python main.py search "réunion projet YODA" --top-k 5
      python main.py search "fournisseur optique" --interactive


GESTION DES TAGS
─────────────────────────────────────────────────────────────────

  python main.py add-tag TAG_NAME AXIS [OPTIONS]

    Ajoute un nouveau tag de classification

    Arguments :
      TAG_NAME             Nom du tag (ex: T_Satellite, P_NewProject)
      AXIS                 Axe de classification (type, projet, fournisseur, etc.)

    Options :
      --description TEXT   Description du tag

    Exemples :
      python main.py add-tag T_Cybersecurite type --description "Sujets cybersécurité"
      python main.py add-tag P_JWST projet --description "Projet James Webb"


  python main.py list-tags [OPTIONS]

    Liste tous les tags de classification

    Options :
      --axis AXIS          Filtre par axe (type, projet, etc.)
      --prefix PREFIX      Filtre par préfixe (T_, P_, F_, etc.)
      --show-inactive      Inclut les tags désactivés

    Exemples :
      python main.py list-tags
      python main.py list-tags --axis type
      python main.py list-tags --prefix P_


  python main.py update-tag TAG_NAME [OPTIONS]

    Modifie un tag existant

    Options :
      --description TEXT   Nouvelle description
      --deactivate         Désactive le tag

    Exemples :
      python main.py update-tag T_OldType --description "Description mise à jour"
      python main.py update-tag T_Obsolete --deactivate


  python main.py delete-tag TAG_NAME [OPTIONS]

    Supprime un tag (désactivation par défaut)

    Options :
      --hard               Suppression permanente (non recommandé)

    Exemples :
      python main.py delete-tag T_OldType
      python main.py delete-tag T_Temp --hard


COMMANDES DATABASE
─────────────────────────────────────────────────────────────────

  python main.py db-migrate

    Exécute les migrations de base de données

  python main.py db-status

    Affiche les statistiques de la base de données

  python main.py embed-all [OPTIONS]

    Génère les embeddings pour tous les emails

    Options :
      --background         Exécute en arrière-plan

    Exemples :
      python main.py embed-all
      python main.py embed-all --background


AIDE ET INFORMATIONS
─────────────────────────────────────────────────────────────────

  python main.py help

    Affiche cette aide détaillée

  python main.py --version

    Affiche la version du programme


═══════════════════════════════════════════════════════════════════
Pour plus d'informations, consultez le README.md
═══════════════════════════════════════════════════════════════════
"""
    print(help_text)


def display_short_help():
    """Display short help for --help flag."""
    short_help = """
Mail Classifier v3.1 - Classification IA d'emails

Commandes principales :
  classify              Classifier les emails Outlook
  search "requête"      Recherche sémantique
  add-tag              Ajouter un tag de classification
  list-tags            Lister les tags
  help                 Aide détaillée

Exemples :
  python main.py classify
  python main.py search "projet YODA"
  python main.py add-tag T_NewType type

Pour l'aide complète : python main.py help
"""
    print(short_help)
