# Mail Classifier v3.1

## Description
Classificateur d'emails Outlook base sur IA multi-axes pour l'industrie spatiale.
Utilise Paradigm API (compatible OpenAI) pour categoriser automatiquement les emails.

## Architecture

```
mail_classifier_v3/
├── mail_classifier/           # Package principal
│   ├── __init__.py           # Exports publics (v3.1.0)
│   ├── api_client.py         # Client API Paradigm
│   ├── banner.py             # Interface CLI banner
│   ├── categorizer.py        # Pipeline de classification IA
│   ├── chunker.py            # Decoupage emails longs
│   ├── cli_commands.py       # Handlers commandes CLI
│   ├── config.py             # Gestion configuration JSON
│   ├── constants.py          # Constantes (OutlookFolders, etc.) [v3.1]
│   ├── database.py           # SQLite ORM
│   ├── email_client.py       # Interface Outlook COM
│   ├── logger.py             # Logging centralise [v3.1]
│   ├── search_engine.py      # Recherche semantique
│   ├── state_manager.py      # Cache conversations
│   ├── tag_manager.py        # CRUD tags
│   ├── utils.py              # Fonctions utilitaires [v3.1]
│   ├── validator.py          # Validation LLM des tags
│   └── vector_store.py       # Embeddings pour recherche
├── config/
│   ├── settings.json         # Configuration principale
│   └── prompt_mail_*.txt     # Prompts par axe
├── migrations/               # Scripts de migration DB
└── main.py                   # CLI entry point
```

## Axes de Classification

Le pipeline traite les axes dans l'ordre suivant:
1. **resume** - Resume de l'email
2. **type** - Type de mail (T_*, S_*)
3. **projet** - Projet/Client/Affaire (P_*, C_*, A_*)
4. **fournisseur** - Fournisseur (F_*)
5. **equipement** - Equipement type et designation (EQT_*, EQ_*)
6. **processus** - Essais et Technique (E_*, TC_*)
7. **qualite** - Qualite, Jalons, Anomalies, NRB (Q_*, J_*, AN_*, NRB_*)

## Conventions

### Prefixes de Categories
- `T_` : Type de mail (Projet, Qualite, Technique, etc.)
- `S_` : Statut (Urgent, Action_Requise, etc.)
- `C_` : Client (AGS, ADS, ESA, etc.)
- `A_` : Affaire (YODA, SICRAL3, etc.)
- `P_` : Projet (Projet_AD, NAC_ERO, etc.)
- `F_` : Fournisseur
- `EQT_` : Type d'equipement - famille produit
- `EQ_` : Designation equipement - instance
- `E_` : Essais et bancs d'essais
- `TC_` : Technique - processus
- `Q_` : Qualite
- `J_` : Jalons
- `AN_` : Anomalies
- `NRB_` : Nonconformance Review Board

### Configuration v3.1
- Les prompts dans `config/prompt_mail_*.txt` definissent le comportement LLM
- **Les regles sont stockees dans la base de donnees**
- `settings.json` definit l'ordre des axes et leurs dependances
- `database.enabled: true` active le stockage des regles en DB

## Commandes CLI

```bash
# Classifier les emails
python main.py classify

# Mode test sans appliquer
python main.py classify --dry-run

# Recherche semantique
python main.py search "query"

# Gestion des tags
python main.py list-tags
python main.py add-tag NOM axe
python main.py db-status
```

## Points d'Attention

### Categorisation C_ et P_ (Clients/Projets)
C_ et P_ sont des listes FERMEES:
- Seules les valeurs definies sont autorisees
- Ne jamais inventer de C_ ou P_ non liste
- En cas de doute sur P_, utiliser P_Projet_AD

### Categorisation F_ (Fournisseurs)
F_ uniquement si explicitement mentionne:
- Nom du fournisseur dans le mail, email, ou signature
- Ne pas deviner a partir d'un composant
- Generalement 0-2 fournisseurs par mail

### Categorisation E_ (Essais)
E_ uniquement si le mail mentionne explicitement:
- Un banc d'essai specifique (BSI, BVT, BCG, etc.)
- Une campagne d'essai planifiee, en cours ou terminee
- PAS juste la mention de "vibrations" ou "chocs"

### Confusion E_ vs EQ_
- `E_` = Essais (axe processus) : BSI, BVT, VIBRATION, etc.
- `EQ_` = Equipement designation (axe equipement) : CAM001, FM1, etc.

### Dependencies entre Axes
Defini dans `settings.json`:
- `fournisseur` depend de `projet`
- `equipement` depend de `projet` et `fournisseur`

## Regles d'Inference v3.1
Appliquees automatiquement apres la classification:
- Si `AN_` present -> ajoute `T_Qualite`, `T_Anomalie`
- Si `NRB_` present -> ajoute `T_Qualite`, `S_Action_Requise`
- Si `J_` present -> ajoute `T_Projet`

## Developpement

### Tests
```bash
python test_integration.py
```

### Base de Donnees
```bash
python main.py db-status
python main.py db-migrate
```

### Modules cles v3.1
- `constants.py` : Constantes nommees (OutlookFolders.INBOX = 6, etc.)
- `logger.py` : Logging centralise (remplace les print())
- `utils.py` : `parse_categories()`, `merge_category_sets()`

### Imports disponibles
```python
from mail_classifier import (
    Config, EmailClient, Categorizer,
    ParadigmAPIClient, StateManager,
    OutlookFolders, parse_categories,
    get_logger, setup_logger
)
```
