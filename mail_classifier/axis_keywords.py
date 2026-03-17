"""
Per-axis keyword and synonym definitions for heuristic classification.

Structure
---------
Each axis entry in ``AXIS_CONFIGS`` maps::

    axis_name → AxisKeywordConfig(
        prefix      = "T_",
        keyword_map = {tag: [kw, ...]},   # base score match
        synonym_map = {tag: [syn, ...]},  # base + SCORE_SYNONYM_BONUS
        regex_patterns = [...],           # serial-number extraction only
        ambiguity_threshold = float,
    )

Scoring recap (from heuristic_engine):
  keyword in subject  → +3
  keyword in body     → +1
  synonym bonus       → +2 additional

Notes
-----
* ``C_`` and ``P_`` are CLOSED lists – populate with your actual referential.
* ``EQ_`` uses regex patterns for serial-number detection in *addition* to
  keyword matching.
* All values in ``keyword_map`` / ``synonym_map`` are matched after
  :class:`TextNormalizer` (lowercase + accent removal).
"""

from typing import Dict, List, Optional

from .heuristic_engine import AxisKeywordConfig


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _cfg(
    axis_name: str,
    prefix: str,
    candidates: Dict[str, Dict],
    regex_patterns: Optional[List[str]] = None,
    ambiguity_threshold: float = 0.15,
    min_score_threshold: float = 0.0,
    max_candidates: int = 5,
) -> AxisKeywordConfig:
    """Build an :class:`AxisKeywordConfig` from a candidates dict.

    Args:
        axis_name:  Axis identifier.
        prefix:     Tag prefix (e.g. ``'T_'``).
        candidates: ``{tag: {"keywords": [...], "synonyms": [...]}}``.
        regex_patterns: For serial-number extraction only.
        ambiguity_threshold: Score-gap ratio below which LLM is called.
        min_score_threshold: Minimum score to keep a candidate.
        max_candidates: Maximum top candidates returned.
    """
    keyword_map = {tag: data.get('keywords', []) for tag, data in candidates.items()}
    synonym_map = {tag: data.get('synonyms', []) for tag, data in candidates.items()}
    return AxisKeywordConfig(
        axis_name=axis_name,
        prefix=prefix,
        keyword_map=keyword_map,
        synonym_map=synonym_map,
        regex_patterns=regex_patterns or [],
        ambiguity_threshold=ambiguity_threshold,
        min_score_threshold=min_score_threshold,
        max_candidates=max_candidates,
    )


# ===========================================================================
# Axis configurations
# ===========================================================================

AXIS_CONFIGS: Dict[str, AxisKeywordConfig] = {}

# ---------------------------------------------------------------------------
# type_mail  (T_)
# ---------------------------------------------------------------------------
AXIS_CONFIGS['type_mail'] = _cfg(
    axis_name='type_mail',
    prefix='T_',
    candidates={
        'T_Demande_Info': {
            'keywords': [
                'demande', 'question', 'renseignement', 'information',
                'request', 'inquiry', 'besoin de', 'pouvez-vous',
                'pourriez-vous', 'souhaitons avoir',
            ],
            'synonyms': ['rfi', 'request for information', 'demande de renseignement'],
        },
        'T_Offre': {
            'keywords': [
                'offre', 'devis', 'proposition', 'cotation', 'prix',
                'tarif', 'quote', 'tender', 'appel offre', 'prix unitaire',
            ],
            'synonyms': ['rfq', 'request for quotation', 'demande de prix'],
        },
        'T_Commande': {
            'keywords': [
                'commande', 'bon de commande', 'purchase order', 'order',
                'achat', 'passation commande',
            ],
            'synonyms': ['bdc', 'po', 'order confirmation', 'confirmation commande'],
        },
        'T_Livraison': {
            'keywords': [
                'livraison', 'expedition', 'delivery', 'expedi', 'recu',
                'reception', 'shipped', 'dispatch', 'bordereau',
            ],
            'synonyms': ['delivery note', 'shipping note', 'bon de livraison'],
        },
        'T_Qualite': {
            'keywords': [
                'qualite', 'non-conformite', 'defaut', 'nc',
                'quality', 'non conformance', 'deviation',
            ],
            'synonyms': ['nrc', 'ncr', 'fiche anomalie', 'quality issue'],
        },
        'T_Anomalie': {
            'keywords': [
                'anomalie', 'defaillance', 'panne', 'erreur',
                'failure', 'fault', 'defect', 'incident technique',
            ],
            'synonyms': ['failure report', 'probleme technique'],
        },
        'T_Reunion': {
            'keywords': [
                'reunion', 'meeting', 'conference', 'invite', 'invitation',
                'kick-off', 'review', 'revue', 'convocation',
            ],
            'synonyms': ['pdr', 'cdr', 'far', 'sar', 'pbr', 'kick off'],
        },
        'T_Projet': {
            'keywords': [
                'planning', 'milestone', 'jalon', 'schedule',
                'roadmap', 'avancement', 'progres',
            ],
            'synonyms': [],
        },
        'T_Rapport': {
            'keywords': [
                'rapport', 'report', 'compte rendu', 'cr', 'summary',
                'synthese', 'bilan', 'flash report',
            ],
            'synonyms': ['meeting minutes', 'minutes de reunion'],
        },
        'T_Action_Requise': {
            'keywords': [
                'action requise', 'action required', 'a faire', 'to do',
                'merci de', 'priere de',
            ],
            'synonyms': ['action item', 'action needed'],
        },
    },
    ambiguity_threshold=0.15,
)

# ---------------------------------------------------------------------------
# statut  (S_)  — exactly ONE per email
# ---------------------------------------------------------------------------
AXIS_CONFIGS['statut'] = _cfg(
    axis_name='statut',
    prefix='S_',
    candidates={
        'S_Urgent': {
            'keywords': [
                'urgent', 'urgence', 'asap', 'immediately', 'critical',
                'critique', 'au plus vite', 'immediatement', 'stop',
            ],
            'synonyms': ['highest priority', 'priorite maximale', 'top priority'],
        },
        'S_Action_Requise': {
            'keywords': [
                'merci de', 'please', 'pouvez-vous', 'could you',
                'priere de', 'nous vous demandons', 'action requise',
                'action required', 'a faire', 'to do',
            ],
            'synonyms': ['action item', 'action needed'],
        },
        'S_En_Attente': {
            'keywords': [
                'en attente', 'waiting', 'pending', 'a venir', 'upcoming',
                'en cours', 'in progress', 'on hold',
            ],
            'synonyms': ['awaiting', 'standby'],
        },
        'S_Information': {
            'keywords': [
                'pour information', 'fyi', 'pour votre information',
                'for your information', 'for information', 'no action required',
                'aucune action', 'a titre informatif',
            ],
            'synonyms': ['for info', 'pour info'],
        },
        'S_Archive': {
            'keywords': [
                'archive', 'clos', 'closed', 'termine', 'done',
                'completed', 'finalise', 'no further action', 'resolu',
            ],
            'synonyms': ['resolved', 'ferme'],
        },
        'S_Classification_incertaine': {
            'keywords': [],
            'synonyms': [],
        },
    },
    ambiguity_threshold=0.20,
    max_candidates=3,
)

# ---------------------------------------------------------------------------
# client  (C_)  — CLOSED LIST, never invent
# ---------------------------------------------------------------------------
AXIS_CONFIGS['client'] = _cfg(
    axis_name='client',
    prefix='C_',
    # ⚠ Replace with your actual client list from the referential
    candidates={
        'C_ArianeGroup': {
            'keywords': ['ariane', 'arianegroup', 'arianespace', 'ariane 6'],
            'synonyms': ['ag'],
        },
        'C_Airbus': {
            'keywords': ['airbus', 'airbus defence', 'ads'],
            'synonyms': ['airbus defense', 'airbus defense and space'],
        },
        'C_Thales': {
            'keywords': ['thales', 'thales alenia', 'tes'],
            'synonyms': ['thalès alenia space', 'tas'],
        },
        'C_CNES': {
            'keywords': ['cnes', 'centre national etudes spatiales'],
            'synonyms': ['agence spatiale francaise'],
        },
        'C_ESA': {
            'keywords': ['esa', 'european space agency'],
            'synonyms': ['agence spatiale europeenne'],
        },
        'C_Safran': {
            'keywords': ['safran', 'snecma', 'herakles'],
            'synonyms': [],
        },
        'C_OHB': {
            'keywords': ['ohb'],
            'synonyms': [],
        },
        'C_ISAE': {
            'keywords': ['isae', 'supaero'],
            'synonyms': [],
        },
    },
    ambiguity_threshold=0.10,
)

# ---------------------------------------------------------------------------
# affaire  (A_)
# ---------------------------------------------------------------------------
AXIS_CONFIGS['affaire'] = _cfg(
    axis_name='affaire',
    prefix='A_',
    # Populate with your actual commercial deals
    candidates={},
    ambiguity_threshold=0.10,
)

# ---------------------------------------------------------------------------
# projet  (P_)  — CLOSED LIST, fallback = P_Projet_AD
# ---------------------------------------------------------------------------
AXIS_CONFIGS['projet'] = _cfg(
    axis_name='projet',
    prefix='P_',
    # ⚠ Replace with your actual project list; P_Projet_AD is the default
    candidates={
        'P_Projet_AD': {
            'keywords': [],
            'synonyms': [],
        },
        'P_GALILEO': {
            'keywords': ['galileo', 'gnss'],
            'synonyms': [],
        },
        'P_SENTINEL': {
            'keywords': ['sentinel', 'copernicus'],
            'synonyms': [],
        },
        'P_JUICE': {
            'keywords': ['juice', 'jupiter'],
            'synonyms': [],
        },
        'P_PLATO': {
            'keywords': ['plato', 'planet transits'],
            'synonyms': [],
        },
        'P_EUCLID': {
            'keywords': ['euclid'],
            'synonyms': [],
        },
        'P_ATHENA': {
            'keywords': ['athena', 'x-ray telescope'],
            'synonyms': [],
        },
        'P_ARIEL': {
            'keywords': ['ariel', 'exoplanet'],
            'synonyms': [],
        },
    },
    ambiguity_threshold=0.10,
)

# ---------------------------------------------------------------------------
# fournisseur  (F_)
# ---------------------------------------------------------------------------
AXIS_CONFIGS['fournisseur'] = _cfg(
    axis_name='fournisseur',
    prefix='F_',
    # Populate with your actual supplier list
    candidates={
        'F_Radiall': {
            'keywords': ['radiall'],
            'synonyms': [],
        },
        'F_Tesat': {
            'keywords': ['tesat'],
            'synonyms': [],
        },
        'F_Amphenol': {
            'keywords': ['amphenol'],
            'synonyms': [],
        },
        'F_Cobham': {
            'keywords': ['cobham'],
            'synonyms': [],
        },
        'F_Saft': {
            'keywords': ['saft'],
            'synonyms': [],
        },
        'F_SatCom': {
            'keywords': ['satcom'],
            'synonyms': ['sat com'],
        },
        'F_Astrium': {
            'keywords': ['astrium'],
            'synonyms': [],
        },
    },
    ambiguity_threshold=0.10,
)

# ---------------------------------------------------------------------------
# equipement_type  (EQT_)
# ---------------------------------------------------------------------------
AXIS_CONFIGS['equipement_type'] = _cfg(
    axis_name='equipement_type',
    prefix='EQT_',
    candidates={
        'EQT_Camera': {
            'keywords': ['camera', 'capteur optique', 'optical sensor', 'imager'],
            'synonyms': ['imaging unit', 'focal plane', 'detector'],
        },
        'EQT_Antenne': {
            'keywords': ['antenne', 'antenna', 'reflecteur', 'reflector', 'feed'],
            'synonyms': ['ant', 'horn', 'diplexer'],
        },
        'EQT_TWTA': {
            'keywords': ['twta', 'travelling wave tube', 'amplificateur onde progressive'],
            'synonyms': ['hpa twta'],
        },
        'EQT_SSPA': {
            'keywords': ['sspa', 'solid state power amplifier'],
            'synonyms': ['amplificateur solide'],
        },
        'EQT_Coupleur': {
            'keywords': ['coupleur', 'coupler', 'divider', 'combiner', 'power divider'],
            'synonyms': [],
        },
        'EQT_Recepteur': {
            'keywords': ['recepteur', 'receiver', 'lna', 'low noise amplifier'],
            'synonyms': [],
        },
        'EQT_Emetteur': {
            'keywords': ['emetteur', 'transmitter', 'tx module'],
            'synonyms': [],
        },
        'EQT_Structure': {
            'keywords': ['structure', 'panneau', 'panel', 'chassis', 'frame'],
            'synonyms': ['primary structure'],
        },
        'EQT_OBC': {
            'keywords': ['obc', 'onboard computer', 'ordinateur bord', 'flight computer'],
            'synonyms': ['on-board computer', 'dpu'],
        },
        'EQT_Batterie': {
            'keywords': ['batterie', 'battery', 'accumulateur', 'cell'],
            'synonyms': ['li-ion', 'nickel hydrogen', 'nhx'],
        },
        'EQT_Panneau_Solaire': {
            'keywords': ['panneau solaire', 'solar panel', 'solar array'],
            'synonyms': ['solar wing', 'photovoltaique', 'sar'],
        },
        'EQT_Propulsion': {
            'keywords': ['propulsion', 'propulseur', 'thruster', 'moteur chimique'],
            'synonyms': ['hydrazine', 'xenon', 'ion engine'],
        },
        'EQT_Connecteur': {
            'keywords': ['connecteur', 'connector', 'harness', 'cable', 'faisceau'],
            'synonyms': ['wiring', 'cabling'],
        },
        'EQT_Gyroscope': {
            'keywords': ['gyroscope', 'gyro', 'rate sensor'],
            'synonyms': ['imu', 'inertial measurement unit'],
        },
        'EQT_StarTracker': {
            'keywords': ['star tracker', 'viseur etoiles', 'stellar sensor'],
            'synonyms': [],
        },
    },
    ambiguity_threshold=0.15,
)

# ---------------------------------------------------------------------------
# equipement_designation  (EQ_)  — uses regex for serial numbers
# ---------------------------------------------------------------------------
AXIS_CONFIGS['equipement_designation'] = _cfg(
    axis_name='equipement_designation',
    prefix='EQ_',
    candidates={
        'EQ_FM1': {
            'keywords': ['fm1', 'flight model 1', 'flight model one'],
            'synonyms': [],
        },
        'EQ_FM2': {
            'keywords': ['fm2', 'flight model 2'],
            'synonyms': [],
        },
        'EQ_FM3': {
            'keywords': ['fm3', 'flight model 3'],
            'synonyms': [],
        },
        'EQ_EQM': {
            'keywords': ['eqm', 'engineering qualification model'],
            'synonyms': [],
        },
        'EQ_EM': {
            'keywords': ['em', 'engineering model'],
            'synonyms': [],
        },
        'EQ_PFM': {
            'keywords': ['pfm', 'proto flight model', 'proto-flight model'],
            'synonyms': [],
        },
        'EQ_QM': {
            'keywords': ['qm', 'qualification model'],
            'synonyms': [],
        },
        'EQ_STM': {
            'keywords': ['stm', 'structural thermal model'],
            'synonyms': [],
        },
        'EQ_BEM': {
            'keywords': ['bem', 'bread board model', 'breadboard'],
            'synonyms': [],
        },
        'EQ_FS': {
            'keywords': ['fs', 'flight spare'],
            'synonyms': [],
        },
    },
    regex_patterns=[
        r'\b[A-Z]{2,4}-\d{3,6}\b',       # CAM-001234, FM-0023
        r'\bSN[:\s]?\d{4,10}\b',          # SN:12345
        r'\bPN[:\s]?[A-Z0-9\-]{4,15}\b',  # PN:ABC-1234
        r'\b\d{4}-[A-Z]{2,4}-\d{3,6}\b',  # 2024-CAM-001
        r'\b[A-Z]{2,3}\d{1,4}\b',         # FM1, FM12, CAM001
    ],
    ambiguity_threshold=0.20,
)

# ---------------------------------------------------------------------------
# essais  (E_)
# ---------------------------------------------------------------------------
AXIS_CONFIGS['essais'] = _cfg(
    axis_name='essais',
    prefix='E_',
    candidates={
        'E_BSI': {
            'keywords': ['bsi', 'banc simulation interface'],
            'synonyms': [],
        },
        'E_BVT': {
            'keywords': ['bvt', 'banc verification thermique'],
            'synonyms': ['thermal vacuum test', 'tv test'],
        },
        'E_BCG': {
            'keywords': ['bcg', 'banc centrifuge'],
            'synonyms': ['centrifuge test', 'acceleration test'],
        },
        'E_VIBRATION': {
            'keywords': [
                'essai vibration', 'vibration test', 'campagne vibration',
                'test vibratoire', 'essais vibratoires',
            ],
            'synonyms': ['shaker test', 'banc vibration'],
        },
        'E_CHOC': {
            'keywords': ['essai choc', 'shock test', 'campagne choc'],
            'synonyms': ['pyro shock', 'pyroshock'],
        },
        'E_EMC': {
            'keywords': [
                'emc', 'electromagnetic compatibility',
                'compatibilite electromagnetique', 'radiated emission',
            ],
            'synonyms': ['cem', 'emf', 'electromagnetic test'],
        },
        'E_ACOUSTIQUE': {
            'keywords': ['essai acoustique', 'acoustic test', 'noise test'],
            'synonyms': ['reverberant chamber'],
        },
        'E_THERMOVIDE': {
            'keywords': [
                'thermo vide', 'thermovide', 'thermal vacuum',
                'essai thermique sous vide', 'tv test',
            ],
            'synonyms': ['tvac'],
        },
        'E_STATIQUE': {
            'keywords': ['essai statique', 'static test', 'load test'],
            'synonyms': [],
        },
        'E_SEPARATION': {
            'keywords': ['essai separation', 'separation test', 'separation mecanique'],
            'synonyms': [],
        },
    },
    ambiguity_threshold=0.15,
)

# ---------------------------------------------------------------------------
# technique  (TC_ / PC_)
# ---------------------------------------------------------------------------
AXIS_CONFIGS['technique'] = _cfg(
    axis_name='technique',
    prefix='TC_',
    candidates={
        'TC_Integration': {
            'keywords': [
                'integration', 'assemblage', 'assembly', 'ait',
                'montage', 'installation', 'integration campaign',
            ],
            'synonyms': ['ait campaign'],
        },
        'TC_Test': {
            'keywords': ['test', 'essai', 'verification', 'validation', 'atv'],
            'synonyms': [],
        },
        'TC_Conception': {
            'keywords': ['conception', 'design', 'dimensionnement', 'calcul'],
            'synonyms': [],
        },
        'TC_Manufacturing': {
            'keywords': ['fabrication', 'manufacturing', 'production', 'usinage'],
            'synonyms': [],
        },
        'TC_Software': {
            'keywords': ['logiciel', 'software', 'firmware', 'code', 'patch'],
            'synonyms': ['sw', 'flight software'],
        },
        'TC_Documentation': {
            'keywords': [
                'documentation', 'document', 'specification', 'icd',
                'interface document', 'drd',
            ],
            'synonyms': ['spec', 'srd', 'idd'],
        },
        'TC_Qualification': {
            'keywords': [
                'qualification', 'qualify', 'qualif', 'qualification test',
            ],
            'synonyms': ['qr'],
        },
        'TC_Acceptance': {
            'keywords': ['acceptance', 'reception', 'acceptance test'],
            'synonyms': ['ar', 'fat'],
        },
        'TC_Maintenance': {
            'keywords': ['maintenance', 'repair', 'reparation', 'overhaul'],
            'synonyms': [],
        },
        'TC_Analyse': {
            'keywords': ['analyse', 'analysis', 'investigation', 'root cause'],
            'synonyms': ['rca', 'root cause analysis'],
        },
    },
    ambiguity_threshold=0.15,
)

# ---------------------------------------------------------------------------
# qualite  (Q_)
# ---------------------------------------------------------------------------
AXIS_CONFIGS['qualite'] = _cfg(
    axis_name='qualite',
    prefix='Q_',
    candidates={
        'Q_Certification': {
            'keywords': ['certification', 'certificat', 'certificate', 'approved'],
            'synonyms': [],
        },
        'Q_Audit': {
            'keywords': ['audit', 'inspection', 'surveillance', 'assessment'],
            'synonyms': [],
        },
        'Q_NonConformite': {
            'keywords': [
                'non-conformite', 'nc', 'non conformance', 'ncr',
                'deviation', 'waiver',
            ],
            'synonyms': ['nrc'],
        },
        'Q_Action_Corrective': {
            'keywords': ['action corrective', 'corrective action', '8d', 'car'],
            'synonyms': [],
        },
        'Q_PPAP': {
            'keywords': ['ppap', 'production part approval'],
            'synonyms': ['first article test', 'fat'],
        },
        'Q_Plan_Qualite': {
            'keywords': ['plan qualite', 'quality plan', 'qap'],
            'synonyms': ['assurance qualite'],
        },
        'Q_PVR': {
            'keywords': ['pvr', 'proces verbal reception', 'acceptance record'],
            'synonyms': [],
        },
        'Q_Traçabilite': {
            'keywords': ['traçabilite', 'traceability', 'pedigree', 'history file'],
            'synonyms': [],
        },
    },
    ambiguity_threshold=0.15,
)

# ---------------------------------------------------------------------------
# jalons  (J_)
# ---------------------------------------------------------------------------
AXIS_CONFIGS['jalons'] = _cfg(
    axis_name='jalons',
    prefix='J_',
    candidates={
        'J_PDR': {
            'keywords': ['pdr', 'preliminary design review', 'revue preliminaire'],
            'synonyms': [],
        },
        'J_CDR': {
            'keywords': ['cdr', 'critical design review', 'revue critique'],
            'synonyms': [],
        },
        'J_QR': {
            'keywords': ['qr', 'qualification review', 'revue qualification'],
            'synonyms': [],
        },
        'J_AR': {
            'keywords': ['ar', 'acceptance review', 'revue reception'],
            'synonyms': [],
        },
        'J_FAR': {
            'keywords': ['far', 'flight acceptance review'],
            'synonyms': [],
        },
        'J_SAR': {
            'keywords': ['sar', 'system acceptance review'],
            'synonyms': [],
        },
        'J_MRR': {
            'keywords': ['mrr', 'manufacturing readiness review'],
            'synonyms': [],
        },
        'J_TRR': {
            'keywords': ['trr', 'test readiness review'],
            'synonyms': [],
        },
        'J_ORR': {
            'keywords': ['orr', 'operations readiness review'],
            'synonyms': [],
        },
        'J_KO': {
            'keywords': ['kick-off', 'kickoff', 'lancement projet', 'reunion lancement'],
            'synonyms': ['project kick-off'],
        },
        'J_SRR': {
            'keywords': ['srr', 'system requirements review', 'revue exigences'],
            'synonyms': [],
        },
    },
    ambiguity_threshold=0.12,
)

# ---------------------------------------------------------------------------
# anomalies  (AN_)
# ---------------------------------------------------------------------------
AXIS_CONFIGS['anomalies'] = _cfg(
    axis_name='anomalies',
    prefix='AN_',
    candidates={
        'AN_Structurelle': {
            'keywords': [
                'fracture', 'fissure', 'crack', 'corrosion', 'deformation',
                'rupture', 'cassure',
            ],
            'synonyms': [],
        },
        'AN_Electrique': {
            'keywords': [
                'court-circuit', 'short circuit', 'surtension', 'overvoltage',
                'panne electrique', 'electrical failure', 'latch-up',
            ],
            'synonyms': [],
        },
        'AN_Software': {
            'keywords': [
                'bug', 'crash', 'erreur logiciel', 'software error',
                'memory corruption', 'reboot inopiné',
            ],
            'synonyms': [],
        },
        'AN_Thermique': {
            'keywords': [
                'surchauffe', 'overheat', 'thermal anomaly',
                'anomalie thermique', 'depassement temperature',
            ],
            'synonyms': [],
        },
        'AN_Fonctionnelle': {
            'keywords': [
                'dysfonctionnement', 'malfunction', 'perte de fonction',
                'loss of function', 'out of spec', 'hors spec',
            ],
            'synonyms': [],
        },
        'AN_Contamination': {
            'keywords': [
                'contamination', 'pollution', 'particule', 'particle',
            ],
            'synonyms': [],
        },
        'AN_Documentaire': {
            'keywords': [
                'erreur documentation', 'document error', 'inconsistance',
                'inconsistency document',
            ],
            'synonyms': [],
        },
    },
    ambiguity_threshold=0.15,
)

# ---------------------------------------------------------------------------
# nrb  (NRB_)
# ---------------------------------------------------------------------------
AXIS_CONFIGS['nrb'] = _cfg(
    axis_name='nrb',
    prefix='NRB_',
    candidates={
        'NRB_Ouvert': {
            'keywords': ['nrb ouvert', 'nrb open', 'open nrb', 'nrb en cours'],
            'synonyms': [],
        },
        'NRB_Clos': {
            'keywords': ['nrb clos', 'nrb closed', 'nrb termine', 'nrb ferme'],
            'synonyms': ['nrb resolved'],
        },
        'NRB_En_Attente': {
            'keywords': ['nrb attente', 'nrb pending', 'nrb on hold'],
            'synonyms': [],
        },
        'NRB_Decision_Requise': {
            'keywords': ['nrb decision', 'nrb vote', 'decision nrb'],
            'synonyms': [],
        },
    },
    ambiguity_threshold=0.15,
)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_axis_config(axis_name: str) -> Optional[AxisKeywordConfig]:
    """Return :class:`AxisKeywordConfig` for *axis_name*, or ``None``."""
    return AXIS_CONFIGS.get(axis_name)


def get_all_axis_names() -> List[str]:
    """Return names of all configured axes."""
    return list(AXIS_CONFIGS.keys())
