"""
Constants and configuration defaults for mail_classifier.
Replaces magic numbers and provides centralized default values.
"""


class OutlookFolders:
    """
    Named constants for Outlook default folder IDs.
    See: OlDefaultFolders Enumeration
    https://docs.microsoft.com/en-us/office/vba/api/outlook.oldefaultfolders
    """
    DELETED_ITEMS = 3
    OUTBOX = 4
    SENT_MAIL = 5
    INBOX = 6
    CALENDAR = 9
    CONTACTS = 10
    JOURNAL = 11
    NOTES = 12
    TASKS = 13
    DRAFTS = 16
    JUNK = 23


# Default configuration values
DEFAULT_CONFIG_PATH = 'config/settings.json'
DEFAULT_CACHE_FILE = '.classifier_cache.json'
DEFAULT_DATABASE_PATH = 'mail_classifier.db'
DEFAULT_EMBEDDINGS_DIR = 'embeddings'

# Token estimation constants
CHARS_PER_TOKEN = 4.0  # Average: 1 token ~ 4 characters
TOKEN_SAFETY_FACTOR = 0.9  # Use 90% of limit for safety margin

# API defaults
DEFAULT_MODEL = 'gpt-4'
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 32000

# Embedding defaults
DEFAULT_EMBEDDING_MODEL = 'multilingual-e5-large'
DEFAULT_EMBEDDING_DIM = 1024
DEFAULT_CACHE_SIZE = 1000
