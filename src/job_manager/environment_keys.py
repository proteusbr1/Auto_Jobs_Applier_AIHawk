# src/job_manager/environment_keys.py
"""
Handles environment variables specific to the job automation workflow.
"""
import os
from loguru import logger
from typing import Optional


class EnvironmentKeys:
    """
    Reads and provides access to specific environment variables controlling
    the automation behavior (e.g., skipping applies, disabling filters).
    """
    # Define expected environment variable keys as constants
    SKIP_APPLY_KEY = "SKIP_APPLY"
    DISABLE_DESC_FILTER_KEY = "DISABLE_DESCRIPTION_FILTER"

    def __init__(self):
        """
        Initializes the EnvironmentKeys class by reading relevant environment variables.
        """
        logger.debug("Initializing EnvironmentKeys...")
        self.skip_apply: bool = self._read_env_key_bool(self.SKIP_APPLY_KEY)
        self.disable_description_filter: bool = self._read_env_key_bool(self.DISABLE_DESC_FILTER_KEY)
        logger.debug(f"EnvironmentKeys initialized: "
                     f"skip_apply={self.skip_apply}, "
                     f"disable_description_filter={self.disable_description_filter}")

    @staticmethod
    def _read_env_key(key: str) -> Optional[str]:
        """Reads an environment variable, returning None if not found."""
        value = os.getenv(key)
        logger.trace(f"Read environment key '{key}': {'Set' if value is not None else 'Not Set'}")
        return value

    @staticmethod
    def _read_env_key_bool(key: str) -> bool:
        """
        Reads an environment variable and interprets it as a boolean.
        Considers "True" (case-insensitive) as True, otherwise False.

        Args:
            key (str): The environment variable name.

        Returns:
            bool: The boolean value.
        """
        value_str = os.getenv(key)
        value_bool = value_str is not None and value_str.strip().lower() == 'true'
        logger.trace(f"Read environment key '{key}' as bool: {value_bool} (Raw value: '{value_str}')")
        return value_bool