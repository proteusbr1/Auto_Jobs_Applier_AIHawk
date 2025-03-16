"""
Implementation of the AIModel interface for OpenAI models.
"""

from loguru import logger
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from src.llm.models.base_model import AIModel


class OpenAIModel(AIModel):
    """
    Implementation of the AIModel interface for OpenAI models.
    """

    def __init__(self, api_key: str, llm_model: str):
        """
        Initialize the OpenAIModel with the specified API key and model name.

        Args:
            api_key (str): The API key for OpenAI.
            llm_model (str): The name of the OpenAI model to use.
        """
        self.model_name = llm_model.lower()
        if llm_model == "o1-mini":
            self.model = ChatOpenAI(model_name=llm_model, openai_api_key=api_key)
        else:
            self.model = ChatOpenAI(model_name=llm_model, openai_api_key=api_key, temperature=0.4)
        logger.debug(f"OpenAIModel initialized with model: {llm_model}")

    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke the OpenAI API with the given prompt.

        Args:
            prompt (str): The input prompt for the OpenAI model.

        Returns:
            BaseMessage: The response from the OpenAI API.

        Raises:
            Exception: If an error occurs while invoking the API.
        """
        logger.debug("Invoking OpenAI API.")
        try:
            response = self.model.invoke(prompt)
            logger.debug("OpenAI API invoked successfully.")
            return response
        except Exception as e:
            logger.error(f"Error invoking OpenAI API: {e}")
            raise
