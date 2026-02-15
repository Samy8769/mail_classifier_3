"""
Configuration management module for mail_classifier.
Handles loading and validation of JSON configuration, including environment variable substitution.
"""

import os
import re
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Any


class ConfigError(Exception):
    """Exception raised for configuration errors."""
    pass


@dataclass
class AxisConfig:
    """Configuration for a single classification axis."""
    name: str
    prompt_file: str
    regles_file: Optional[str]
    dependencies: List[str]
    prompt: str = None
    rules: Optional[str] = None


class Config:
    """Main configuration class for mail_classifier."""

    def __init__(self, config_data: Dict[str, Any], config_dir: str):
        """
        Initialize configuration from parsed YAML data.

        Args:
            config_data: Dictionary containing configuration
            config_dir: Directory containing config files
        """
        self.config_dir = config_dir
        self.api = config_data.get('api', {})
        self.proxy = config_data.get('proxy', {})
        self.outlook = config_data.get('outlook', {})
        self.classification = config_data.get('classification', {})
        self.state = config_data.get('state', {})

        # V2.0: Enhanced configuration sections
        self.database = config_data.get('database', {'enabled': False})
        self.chunking = config_data.get('chunking', {'enabled': False})
        self.embeddings = config_data.get('embeddings', {'enabled': False})
        self.validation = config_data.get('validation', {'enabled': True})
        self.search = config_data.get('search', {})

        # Load classification axes with prompts and rules
        self._load_classification_axes()

    @classmethod
    def load(cls, config_path: str = 'config/settings.json') -> 'Config':
        """
        Load configuration from JSON file.

        Args:
            config_path: Path to configuration file

        Returns:
            Config object

        Raises:
            ConfigError: If configuration loading fails
        """
        if not os.path.exists(config_path):
            raise ConfigError(f"Configuration file not found: {config_path}")

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Failed to parse JSON: {e}")
        except Exception as e:
            raise ConfigError(f"Failed to load configuration: {e}")

        # Substitute environment variables
        config_data = cls._substitute_env_vars(config_data)

        # Get config directory
        config_dir = os.path.dirname(os.path.abspath(config_path))

        # Create and validate config
        config = cls(config_data, config_dir)
        config._validate()

        return config

    @staticmethod
    def _substitute_env_vars(data: Any) -> Any:
        """
        Recursively substitute environment variables in configuration.
        Replaces ${VAR_NAME} with environment variable value.

        Args:
            data: Configuration data (dict, list, or string)

        Returns:
            Data with environment variables substituted
        """
        if isinstance(data, dict):
            return {k: Config._substitute_env_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [Config._substitute_env_vars(item) for item in data]
        elif isinstance(data, str):
            # Find ${VAR_NAME} patterns
            pattern = r'\$\{([^}]+)\}'
            matches = re.findall(pattern, data)

            for var_name in matches:
                env_value = os.environ.get(var_name)
                if env_value:
                    data = data.replace(f'${{{var_name}}}', env_value)
                # If env var not set, leave placeholder (will be caught in validation)

            return data
        else:
            return data

    def _load_classification_axes(self):
        """
        Load prompts for each classification axis.
        Rules are now loaded from database, not files.
        """
        axes_config = self.classification.get('axes', [])
        loaded_axes = []

        for axis_data in axes_config:
            # Create AxisConfig object
            axis = AxisConfig(
                name=axis_data['name'],
                prompt_file=axis_data['prompt_file'],
                regles_file=axis_data.get('regles_file'),  # Kept for backward compat
                dependencies=axis_data.get('dependencies', [])
            )

            # Load prompt file
            prompt_path = os.path.join(self.config_dir, axis.prompt_file)
            try:
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    axis.prompt = f.read()
            except FileNotFoundError:
                raise ConfigError(f"Prompt file not found: {prompt_path}")
            except Exception as e:
                raise ConfigError(f"Failed to load prompt file {prompt_path}: {e}")

            # v3.0: Rules are loaded from database, not files
            # axis.rules will be populated by categorizer using db.reconstruct_full_rules()
            # For backward compatibility, optionally load from file if specified
            if axis.regles_file and self.database.get('enabled', False) is False:
                rules_path = os.path.join(self.config_dir, axis.regles_file)
                try:
                    with open(rules_path, 'r', encoding='utf-8') as f:
                        axis.rules = f.read()
                except FileNotFoundError:
                    # Not an error in v3.0 - rules come from DB
                    pass
                except Exception:
                    pass

            loaded_axes.append(axis)

        # Store loaded axes
        self.classification['axes'] = loaded_axes

    def _validate(self):
        """Validate configuration values."""
        # Validate API configuration
        if not self.api.get('base_url'):
            raise ConfigError("API base_url is required")

        api_key = self.api.get('api_key', '')
        if not api_key or api_key.startswith('${'):
            raise ConfigError(
                "API key not configured. Set PARADIGM_API_KEY environment variable "
                "or update api_key in settings.yaml"
            )

        if not self.api.get('model'):
            raise ConfigError("API model is required")

        # Validate temperature
        temp = self.api.get('temperature', 0.2)
        if not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
            raise ConfigError("Temperature must be a number between 0 and 2")

        # Validate Outlook configuration
        if not self.outlook.get('default_folders'):
            raise ConfigError("At least one default folder must be specified")

        if not self.outlook.get('ai_trigger_category'):
            raise ConfigError("AI trigger category is required")

        if not self.outlook.get('done_marker_category'):
            raise ConfigError("Done marker category is required")

        # Validate classification axes
        if not self.classification.get('axes'):
            raise ConfigError("At least one classification axis must be configured")

        # Validate state configuration
        if self.state.get('enabled') and not self.state.get('cache_file'):
            raise ConfigError("Cache file path required when state is enabled")

    def get_axis_by_name(self, name: str) -> Optional[AxisConfig]:
        """
        Get axis configuration by name.

        Args:
            name: Axis name

        Returns:
            AxisConfig or None if not found
        """
        for axis in self.classification['axes']:
            if axis.name == name:
                return axis
        return None
