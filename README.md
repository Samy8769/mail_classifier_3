# Mail Classifier v3.1

Classification automatique d'emails Outlook par IA multi-axes pour l'industrie spatiale.

## Fonctionnalites

- **Classification multi-axes** : Type, Projet, Fournisseur, Equipement, Processus, Qualite
- **Chunking intelligent** : Gere les emails >32K tokens automatiquement
- **Base de donnees SQLite** : Stockage structure des emails, tags et classifications
- **Recherche semantique** : Trouve des emails par sens, pas seulement mots-cles
- **Validation LLM** : Verifie automatiquement la conformite des tags
- **Gestion dynamique des tags** : CRUD via CLI ou base de donnees
- **Cache intelligent** : Evite le retraitement des conversations deja classifiees

## Installation

### Prerequis

- Python 3.8+
- Microsoft Outlook (Windows)
- Acces API Paradigm (ou compatible OpenAI)

### Installation des dependances

```bash
pip install -r requirements.txt
```

### Configuration initiale

1. Configurer la cle API:
```bash
set PARADIGM_API_KEY=votre_cle_api
```

2. Migrer les tags vers la base de donnees:
```bash
python migrations/002_populate_tags.py
```

3. Verifier l'installation:
```bash
python test_integration.py
```

## Utilisation

### Classification d'emails

```bash
# Classification standard
python main.py classify

# Dossier specifique
python main.py classify --folder "Sent Items"

# Mode test (sans appliquer les categories)
python main.py classify --dry-run

# Mode verbeux
python main.py classify --verbose
```

### Recherche semantique

```bash
# Recherche simple
python main.py search "anomalies satellite YODA"

# Top 5 resultats
python main.py search "problemes qualite" --top-k 5

# Mode interactif
python main.py search "defauts optiques" --interactive
```

### Gestion des tags

```bash
# Lister tous les tags
python main.py list-tags

# Lister par axe
python main.py list-tags --axis type

# Ajouter un tag
python main.py add-tag T_Cybersecurite type --description "Sujets cybersecurite"

# Modifier un tag
python main.py update-tag T_OldName --description "Nouvelle description"

# Supprimer un tag
python main.py delete-tag T_Obsolete
```

### Administration

```bash
# Statistiques base de donnees
python main.py db-status

# Executer les migrations
python main.py db-migrate

# Generer les embeddings (pour la recherche)
python main.py embed-all

# Aide detaillee
python main.py help
```

## Architecture

```
mail_classifier_v3/
├── mail_classifier/           # Package principal
│   ├── __init__.py           # Exports publics (v3.1.0)
│   ├── api_client.py         # Client API Paradigm/OpenAI
│   ├── banner.py             # Interface CLI banner
│   ├── categorizer.py        # Pipeline de classification IA
│   ├── chunker.py            # Decoupage emails longs
│   ├── cli_commands.py       # Handlers commandes CLI
│   ├── config.py             # Gestion configuration JSON
│   ├── constants.py          # Constantes (OutlookFolders, etc.) [NEW v3.1]
│   ├── database.py           # SQLite ORM
│   ├── email_client.py       # Interface Outlook COM
│   ├── logger.py             # Logging centralise [NEW v3.1]
│   ├── search_engine.py      # Recherche semantique
│   ├── state_manager.py      # Cache conversations
│   ├── tag_manager.py        # CRUD tags
│   ├── utils.py              # Fonctions utilitaires [REFACTORED v3.1]
│   ├── validator.py          # Validation LLM des tags
│   └── vector_store.py       # Stockage embeddings
├── config/
│   ├── settings.json         # Configuration principale
│   └── prompt_mail_*.txt     # Prompts par axe
├── migrations/
│   ├── 001_initial_schema.sql
│   ├── 002_populate_tags.py
│   ├── 003_migrate_rules_to_db.sql
│   └── 004_populate_all_rules.py
├── main.py                   # Point d'entree CLI
└── requirements.txt          # Dependances
```

## Configuration

### Fichier `config/settings.json`

```json
{
  "api": {
    "base_url": "https://paradigm.sodern.net:30443/api/v2",
    "api_key": "${PARADIGM_API_KEY}",
    "model": "alfred-4.2",
    "temperature": 0.2
  },
  "database": {
    "enabled": true,
    "db_path": "mail_classifier.db"
  },
  "chunking": {
    "enabled": true,
    "max_tokens": 32000,
    "overlap_tokens": 200
  },
  "embeddings": {
    "enabled": false,
    "model": "multilingual-e5-large",
    "dimension": 1024
  },
  "validation": {
    "enabled": true,
    "auto_correct": true
  }
}
```

### Activer la recherche semantique

1. Modifier `config/settings.json`:
```json
"embeddings": {
  "enabled": true
}
```

2. Generer les embeddings:
```bash
python main.py embed-all
```

## Axes de Classification

| Axe | Prefixes | Description |
|-----|----------|-------------|
| Type | `T_`, `S_` | Type de mail et statut |
| Projet | `P_`, `C_`, `A_` | Projet, Client, Affaire |
| Fournisseur | `F_` | Fournisseurs |
| Equipement | `EQT_`, `EQ_` | Type et designation equipement |
| Processus | `E_`, `TC_` | Essais et technique |
| Qualite | `Q_`, `J_`, `AN_`, `NRB_` | Qualite, jalons, anomalies |

## Utilisation en tant que bibliotheque

```python
from mail_classifier import (
    Config, EmailClient, Categorizer,
    ParadigmAPIClient, StateManager,
    OutlookFolders, parse_categories
)

# Charger la configuration
config = Config.load('config/settings.json')

# Initialiser les composants
api_client = ParadigmAPIClient(config.api, config.proxy)
state_manager = StateManager(config.state, config.outlook)
email_client = EmailClient(config.outlook)
categorizer = Categorizer(config, api_client, state_manager)

# Traiter les emails
folder = email_client.get_folder_by_name_or_number(OutlookFolders.INBOX)
emails = email_client.get_emails_by_category(folder, 'AI', exclude_category='AI done')
conversations = email_client.group_by_conversation(emails)

for conv_id, conv_emails in conversations.items():
    categories = categorizer.categorize_conversation(conv_id, conv_emails)
    email_client.apply_categories_to_conversation(folder, conv_id, categories)
```

## Performances

| Operation | Temps |
|-----------|-------|
| Classification (email standard) | 8-12s |
| Classification (email chunke) | 15-40s |
| Recherche (1000 chunks) | <1s |
| Generation embedding (par chunk) | 200-500ms |

**Limite recommandee** : <10,000 chunks pour performances optimales de recherche.

## Depannage

### "No tags found in database"
```bash
python migrations/002_populate_tags.py
```

### "API key not configured"
```bash
set PARADIGM_API_KEY=votre_cle_api
```

### Performance lente
- Desactiver embeddings si non utilises: `"embeddings.enabled": false`
- La validation ajoute ~1-2s par conversation

### Email pas chunke
- Verifier `"chunking.enabled": true`
- L'email doit depasser 32K tokens (~128K caracteres)

## Changelog v3.1

### Corrections
- **Bug critique** : Corrige l'inversion des champs `sender_email`/`sender_name`
- **Securite** : Suppression du fichier legacy avec cle API exposee

### Code mort supprime
- Methode `_build_axis_prompt()` (wrapper inutile)
- Methode `reconstruct_rules_from_tags()` (jamais appelee)
- Fonction `format_categories_for_display()` (jamais utilisee)

### Optimisations
- Chargement batch des embeddings (resout N+1)
- Filtre Restrict pour Outlook (evite iteration complete)

### Nouveaux modules
- `constants.py` : Constantes nommees (OutlookFolders, etc.)
- `logger.py` : Logging centralise
- `utils.py` : Fonctions utilitaires refactorisees

### Qualite du code
- Correction des bare `except:` clauses
- Correction des type hints (`any` -> `Any`)
- Import `Set` inutilise supprime

## Licence

MIT

## Support

Pour questions ou problemes:
1. Consulter ce README
2. Verifier la configuration dans `config/settings.json`
3. Executer les tests: `python test_integration.py`
