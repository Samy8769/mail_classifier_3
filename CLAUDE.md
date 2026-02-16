# Mail Classifier v3.2

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
│   └── prompt_mail_*.txt     # Prompts par axe (1 fichier par prefixe)
├── migrations/               # Scripts de migration DB
└── main.py                   # CLI entry point
```

## Axes de Classification

Chaque prefixe est traite par un appel LLM independant.
Le pipeline traite les axes dans l'ordre suivant:

1. **resume** - Resume de l'email
2. **type_mail** - Type de mail (T_*)
3. **statut** - Statut et action (S_*)
4. **client** - Client final (C_*)
5. **affaire** - Affaire commerciale (A_*)
6. **projet** - Projet technique (P_*)
7. **fournisseur** - Fournisseur (F_*)
8. **equipement_type** - Type d'equipement / famille produit (EQT_*)
9. **equipement_designation** - Designation equipement / instance (EQ_*)
10. **essais** - Essais et bancs d'essais (E_*)
11. **technique** - Processus technique (TC_*)
12. **qualite** - Qualite (Q_*)
13. **jalons** - Jalons et revues projet (J_*)
14. **anomalies** - Anomalies et non-conformites (AN_*)
15. **nrb** - Nonconformance Review Board (NRB_*)

## Conventions

### Prefixes de Categories
- `T_` : Type de mail (axe type_mail)
- `S_` : Statut (axe statut)
- `C_` : Client (axe client)
- `A_` : Affaire (axe affaire)
- `P_` : Projet (axe projet)
- `F_` : Fournisseur (axe fournisseur)
- `EQT_` : Type d'equipement - famille produit (axe equipement_type)
- `EQ_` : Designation equipement - instance (axe equipement_designation)
- `E_` : Essais et bancs d'essais (axe essais)
- `TC_` : Technique - processus (axe technique)
- `Q_` : Qualite (axe qualite)
- `J_` : Jalons (axe jalons)
- `AN_` : Anomalies (axe anomalies)
- `NRB_` : Nonconformance Review Board (axe nrb)

### Configuration v3.2
- Les prompts dans `config/prompt_mail_*.txt` definissent le comportement LLM
- **Un fichier prompt et un fichier regles par prefixe**
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

### Categorisation C_ (Clients)
C_ est une liste FERMEE:
- Seules les valeurs definies sont autorisees
- Ne jamais inventer de C_ non liste

### Categorisation P_ (Projets)
P_ est une liste FERMEE:
- Ne jamais inventer de P_ non liste
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
- `E_` = Essais (axe essais) : BSI, BVT, VIBRATION, etc.
- `EQ_` = Equipement designation (axe equipement_designation) : CAM001, FM1, etc.

### Dependencies entre Axes
Defini dans `settings.json`:
- `statut` depend de `type_mail`
- `affaire` depend de `client`
- `projet` depend de `client` et `affaire`
- `fournisseur` depend de `projet`
- `equipement_type` depend de `projet` et `fournisseur`
- `equipement_designation` depend de `projet`, `fournisseur` et `equipement_type`
- `essais` et `technique` dependent de `projet`
- `qualite`, `jalons`, `anomalies` dependent de `type_mail` et `projet`
- `nrb` depend de `type_mail`, `projet` et `anomalies`

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
# Migration pour splitter les axes existants:
python migrations/007_split_all_axes.py
```

### Modules cles v3.2
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
