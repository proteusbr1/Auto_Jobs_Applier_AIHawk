"""
Implementation of the AIModel interface for Gemini models.
"""

from loguru import logger
from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI, HarmBlockThreshold, HarmCategory

from src.llm.models.base_model import AIModel


class GeminiModel(AIModel):
    """
    Implementation of the AIModel interface for Gemini models.
    """

    def __init__(self, api_key: str, llm_model: str):
        """
        Initialize the GeminiModel with the specified API key and model name.

        Args:
            api_key (str): The API key for Gemini.
            llm_model (str): The name of the Gemini model to use.
        """
        self.model = ChatGoogleGenerativeAI(
            model=llm_model,
            google_api_key=api_key,
            safety_settings={
                HarmCategory.HARM_CATEGORY_UNSPECIFIED: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DEROGATORY: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_TOXICITY: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_VIOLENCE: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUAL: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_MEDICAL: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE
            }
        )
        logger.debug(f"GeminiModel initialized with model: {llm_model}")

    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke the Gemini API with the given prompt.

        Args:
            prompt (str): The input prompt for the Gemini model.

        Returns:
            BaseMessage: The response from the Gemini API.

        Raises:
            Exception: If an error occurs while invoking the API.
        """
        logger.debug("Invoking Gemini API.")
        try:
            response = self.model.invoke(prompt)
            logger.debug("Gemini API invoked successfully.")
            return response
        except Exception as e:
            logger.error(f"Error invoking Gemini API: {e}")
            raise
