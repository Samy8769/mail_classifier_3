"""
Test bootstrap: stubs all external dependencies so the pipeline modules
can be imported without pywin32, openai, httpx, numpy, etc.

Usage: import test_bootstrap as the first import in each test file.
"""

import sys
import types
import os

# Stub all external packages that mail_classifier depends on
_STUBS = [
    'win32com', 'win32com.client', 'pythoncom',
    'openai', 'httpx', 'numpy',
]

for mod_name in _STUBS:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

# Now replace mail_classifier's __init__ with a lightweight version
# that doesn't re-export everything (which triggers the full import chain).
project_root = os.path.dirname(os.path.abspath(__file__))
pkg_path = os.path.join(project_root, 'mail_classifier')

# Create a lightweight package module
pkg = types.ModuleType('mail_classifier')
pkg.__path__ = [pkg_path]
pkg.__package__ = 'mail_classifier'
pkg.__file__ = os.path.join(pkg_path, '__init__.py')
sys.modules['mail_classifier'] = pkg

# Stub out modules that our pipeline modules import from the package
# but that have heavy external deps themselves.
# The logger module is pure-Python and needed, so import it for real.
import importlib.util

# Load logger for real (no external deps)
_logger_spec = importlib.util.spec_from_file_location(
    'mail_classifier.logger',
    os.path.join(pkg_path, 'logger.py')
)
_logger_mod = importlib.util.module_from_spec(_logger_spec)
sys.modules['mail_classifier.logger'] = _logger_mod
_logger_spec.loader.exec_module(_logger_mod)

# Stub utils with a minimal parse_categories
_utils = types.ModuleType('mail_classifier.utils')


def _parse_categories(text):
    """Minimal stub matching real parse_categories behavior."""
    if not text:
        return []
    return [t.strip() for t in text.split(',') if t.strip()]


_utils.parse_categories = _parse_categories
sys.modules['mail_classifier.utils'] = _utils
