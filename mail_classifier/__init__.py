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
from .email_client import EmailClient
from .categorizer import Categorizer
from .api_client import ParadigmAPIClient, APIError
from .state_manager import StateManager
from .constants import OutlookFolders
from .utils import parse_categories, merge_category_sets
from .logger import get_logger, setup_logger

__all__ = [
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
]
