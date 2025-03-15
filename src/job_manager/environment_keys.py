"""
Module for handling environment variables used in the AIHawk Job Manager.
"""
import os
from loguru import logger


class EnvironmentKeys:
    """
    Class for handling environment variables used in the AIHawk Job Manager.
    """
    def __init__(self):
        """
        Initialize the EnvironmentKeys class by reading environment variables.
        """
        logger.debug("Initializing EnvironmentKeys")
        self.skip_apply = self._read_env_key_bool("SKIP_APPLY")
        self.disable_description_filter = self._read_env_key_bool("DISABLE_DESCRIPTION_FILTER")
        logger.debug(f"EnvironmentKeys initialized: skip_apply={self.skip_apply}, disable_description_filter={self.disable_description_filter}")

    @staticmethod
    def _read_env_key(key: str) -> str:
        """
        Read an environment variable.

        Args:
            key (str): The name of the environment variable.

        Returns:
            str: The value of the environment variable, or an empty string if not found.
        """
        value = os.getenv(key, "")
        logger.debug(f"Read environment key {key}: {value}")
        return value

    @staticmethod
    def _read_env_key_bool(key: str) -> bool:
        """
        Read an environment variable as a boolean.

        Args:
            key (str): The name of the environment variable.

        Returns:
            bool: True if the environment variable is "True", False otherwise.
        """
        value = os.getenv(key) == "True"
        logger.debug(f"Read environment key {key} as bool: {value}")
        return value
