"""
Adapter class to abstract the interaction with different AI models.
"""

from typing import Dict

from loguru import logger

from src.llm.models import (
    AIModel,
    OpenAIModel,
    ClaudeModel,
    OllamaModel,
    GeminiModel,
    HuggingFaceModel
)


class AIAdapter:
    """
    Adapter class to abstract the interaction with different AI models.
    """

    def __init__(self, config: Dict, api_key: str):
        """
        Initialize the AIAdapter with the given configuration and API key.

        Args:
            config (Dict): Configuration dictionary containing model details.
            api_key (str): The API key for the selected AI model.
        """
        self.model = self._create_model(config, api_key)
        logger.debug("AIAdapter initialized with model.")

    def _create_model(self, config: Dict, api_key: str) -> AIModel:
        """
        Create an instance of the appropriate AIModel based on the configuration.

        Args:
            config (Dict): Configuration dictionary containing model details.
            api_key (str): The API key for the selected AI model.

        Returns:
            AIModel: An instance of a subclass of AIModel.

        Raises:
            ValueError: If the model type specified in the configuration is unsupported.
        """
        llm_model_type = config.get('llm_model_type')
        llm_model = config.get('llm_model')
        llm_api_url = config.get('llm_api_url', "")

        logger.debug(f"Using model type: {llm_model_type} with model: {llm_model}")

        if llm_model_type == "openai":
            return OpenAIModel(api_key, llm_model)
        elif llm_model_type == "claude":
            return ClaudeModel(api_key, llm_model)
        elif llm_model_type == "ollama":
            return OllamaModel(llm_model, llm_api_url)
        elif llm_model_type == "gemini":
            return GeminiModel(api_key, llm_model)
        elif llm_model_type == "huggingface":
            return HuggingFaceModel(api_key, llm_model)
        else:
            logger.error(f"Unsupported model type: {llm_model_type}")
            raise ValueError(f"Unsupported model type: {llm_model_type}")

    def invoke(self, prompt: str) -> str:
        """
        Invoke the selected AI model with the given prompt.

        Args:
            prompt (str): The input prompt for the AI model.

        Returns:
            str: The response from the AI model.

        Raises:
            Exception: If an error occurs while invoking the model.
        """
        logger.debug("AIAdapter invoking model.")
        try:
            return self.model.invoke(prompt)
        except Exception as e:
            logger.error(f"Error invoking model through AIAdapter: {e}")
            raise
