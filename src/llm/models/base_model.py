"""
Base model interface for AI models.
"""

from abc import ABC, abstractmethod


class AIModel(ABC):
    """
    Abstract base class for AI models.
    Defines the interface that all AI models must implement.
    """

    @abstractmethod
    def invoke(self, prompt: str) -> str:
        """
        Invoke the AI model with the given prompt.

        Args:
            prompt (str): The input prompt for the AI model.

        Returns:
            str: The text response from the AI model.
        """
        pass
