"""
Mail Classifier - AI-powered email classification for Outlook

A modular package for classifying Outlook emails using AI with multi-axis categorization.

Example usage:
    from mail_classifier import Config, EmailClient, Categorizer, ParadigmAPIClient, StateManager

    # Load configuration
    config = Config.load('config/settings.json')

    # Initialize components
    api = ParadigmAPIClient(config.api, config.proxy)
    state = StateManager(config.state, config.outlook)
    email_client = EmailClient(config.outlook)
    categorizer = Categorizer(config, api, state)

    # Process emails
    folder = email_client.get_folder_by_name_or_number('Inbox')
    emails = email_client.get_emails_by_category(folder, 'AI', exclude_category='AI done')
    conversations = email_client.group_by_conversation(emails)

    for conv_id, conv_emails in conversations.items():
        categories = categorizer.categorize_conversation(conv_id, conv_emails)
        email_client.apply_categories_to_conversation(folder, conv_id, categories)
"""

__version__ = "3.1.0"
__author__ = "Your Name"
__license__ = "MIT"

from .config import Config, ConfigError, AxisConfig
from .constants import OutlookFolders
from .utils import parse_categories, merge_category_sets
from .logger import get_logger, setup_logger

# Optional: requires openai, httpx
try:
    from .api_client import ParadigmAPIClient, APIError
    from .state_manager import StateManager
except ImportError:
    ParadigmAPIClient = None  # type: ignore[assignment,misc]
    APIError = None           # type: ignore[assignment,misc]
    StateManager = None       # type: ignore[assignment,misc]

# Windows-only Outlook COM components (not available on Linux/macOS)
try:
    from .email_client import EmailClient
    from .categorizer import Categorizer
except ImportError:
    EmailClient = None  # type: ignore[assignment,misc]
    Categorizer = None  # type: ignore[assignment,misc]

# v3.2 – Hybrid heuristic + LLM pipeline
from .heuristic_engine import (
    TextNormalizer,
    AhoCorasickMatcher,
    SerialNumberExtractor,
    AxisKeywordConfig,
    AxisHeuristicPipeline,
    AxisHeuristicResult,
    CandidateMatch,
)
from .axis_keywords import AXIS_CONFIGS, get_axis_config, get_all_axis_names
from .hybrid_pipeline import (
    HybridClassificationPipeline,
    HybridAxisClassifier,
    HybridClassificationOutput,
    AxisClassificationResult,
)

__all__ = [
    # Core
    'Config',
    'ConfigError',
    'AxisConfig',
    'EmailClient',
    'Categorizer',
    'ParadigmAPIClient',
    'APIError',
    'StateManager',
    'OutlookFolders',
    'parse_categories',
    'merge_category_sets',
    'get_logger',
    'setup_logger',
    # Heuristic engine (v3.2)
    'TextNormalizer',
    'AhoCorasickMatcher',
    'SerialNumberExtractor',
    'AxisKeywordConfig',
    'AxisHeuristicPipeline',
    'AxisHeuristicResult',
    'CandidateMatch',
    # Axis keyword configs (v3.2)
    'AXIS_CONFIGS',
    'get_axis_config',
    'get_all_axis_names',
    # Hybrid pipeline (v3.2)
    'HybridClassificationPipeline',
    'HybridAxisClassifier',
    'HybridClassificationOutput',
    'AxisClassificationResult',
]
