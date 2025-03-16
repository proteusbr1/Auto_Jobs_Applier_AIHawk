"""
Implementation of the AIModel interface for Ollama models.
"""

from loguru import logger
from langchain_core.messages import BaseMessage
from langchain_ollama import ChatOllama

from src.llm.models.base_model import AIModel


class OllamaModel(AIModel):
    """
    Implementation of the AIModel interface for Ollama models.
    """

    def __init__(self, llm_model: str, llm_api_url: str):
        """
        Initialize the OllamaModel with the specified model name and API URL.

        Args:
            llm_model (str): The name of the Ollama model to use.
            llm_api_url (str): The API URL for Ollama.
        """
        if llm_api_url:
            logger.debug(f"Using Ollama with API URL: {llm_api_url}")
            self.model = ChatOllama(model=llm_model, base_url=llm_api_url)
        else:
            self.model = ChatOllama(model=llm_model)
            logger.debug(f"Using Ollama with default API URL for model: {llm_model}")

    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke the Ollama API with the given prompt.

        Args:
            prompt (str): The input prompt for the Ollama model.

        Returns:
            BaseMessage: The response from the Ollama API.

        Raises:
            Exception: If an error occurs while invoking the API.
        """
        logger.debug("Invoking Ollama API.")
        try:
            response = self.model.invoke(prompt)
            logger.debug("Ollama API invoked successfully.")
            return response
        except Exception as e:
            logger.error(f"Error invoking Ollama API: {e}")
            raise
