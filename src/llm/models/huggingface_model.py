"""
Implementation of the AIModel interface for Hugging Face models.
"""

from loguru import logger
from langchain_core.messages import BaseMessage
from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace

from src.llm.models.base_model import AIModel


class HuggingFaceModel(AIModel):
    """
    Implementation of the AIModel interface for Hugging Face models.
    """

    def __init__(self, api_key: str, llm_model: str):
        """
        Initialize the HuggingFaceModel with the specified API key and model name.

        Args:
            api_key (str): The API key for Hugging Face.
            llm_model (str): The name of the Hugging Face model to use.
        """
        self.model = HuggingFaceEndpoint(repo_id=llm_model, huggingfacehub_api_token=api_key, temperature=0.4)
        self.chatmodel = ChatHuggingFace(llm=self.model)
        logger.debug(f"HuggingFaceModel initialized with model: {llm_model}")

    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke the Hugging Face API with the given prompt.

        Args:
            prompt (str): The input prompt for the Hugging Face model.

        Returns:
            BaseMessage: The response from the Hugging Face API.

        Raises:
            Exception: If an error occurs while invoking the API.
        """
        logger.debug("Invoking Hugging Face API.")
        try:
            response = self.chatmodel.invoke(prompt)
            logger.debug("Hugging Face API invoked successfully.")
            return response
        except Exception as e:
            logger.error(f"Error invoking Hugging Face API: {e}")
            raise
