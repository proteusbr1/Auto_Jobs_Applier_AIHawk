"""
Implementation of the AIModel interface for Claude models.
"""

from loguru import logger
from langchain_core.messages import BaseMessage
from langchain_anthropic import ChatAnthropic

from src.llm.models.base_model import AIModel


class ClaudeModel(AIModel):
    """
    Implementation of the AIModel interface for Claude models.
    """

    def __init__(self, api_key: str, llm_model: str):
        """
        Initialize the ClaudeModel with the specified API key and model name.

        Args:
            api_key (str): The API key for Claude.
            llm_model (str): The name of the Claude model to use.
        """
        self.model = ChatAnthropic(model=llm_model, api_key=api_key, temperature=0.4)
        logger.debug(f"ClaudeModel initialized with model: {llm_model}")

    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke the Claude API with the given prompt.

        Args:
            prompt (str): The input prompt for the Claude model.

        Returns:
            BaseMessage: The response from the Claude API.

        Raises:
            Exception: If an error occurs while invoking the API.
        """
        logger.debug("Invoking Claude API.")
        try:
            response = self.model.invoke(prompt)
            logger.debug("Claude API invoked successfully.")
            return response
        except Exception as e:
            logger.error(f"Error invoking Claude API: {e}")
            raise
