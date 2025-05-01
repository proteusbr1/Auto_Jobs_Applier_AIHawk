# src/llm/models/gemini_model.py
"""
Concrete implementation of the AIModel interface for Google Gemini models.
Uses the `langchain-google-genai` package.
"""

from typing import Any, Union, List, Dict, Optional

from loguru import logger
# Ensure necessary LangChain components are imported
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage # For type hint
from langchain_core.prompt_values import ChatPromptValue # For type hint
# Import custom exceptions and base class
from .base_model import AIModel, LLMInvocationError, ConfigurationError
# Optionally import specific Google exceptions
# from google.api_core.exceptions import ResourceExhausted, PermissionDenied, Unauthenticated


class GeminiModel(AIModel):
    """
    AIModel implementation for interacting with Google's Gemini models.
    """

    def __init__(
        self,
        model_name: str,
        api_key: Optional[str] = None,
        temperature: Optional[float] = None,
        **kwargs: Any
    ):
        """
        Initializes the GeminiModel.

        Args:
            model_name (str): The specific Gemini model identifier (e.g., "gemini-1.5-pro-latest").
            api_key (Optional[str]): The Google AI API key. If None, it attempts to use the
                                     `GOOGLE_API_KEY` environment variable.
            temperature (Optional[float]): The sampling temperature. Defaults to `AIModel.DEFAULT_TEMPERATURE`.
            **kwargs: Additional keyword arguments passed directly to `ChatGoogleGenerativeAI`.
        """
        resolved_api_key = api_key
        effective_kwargs = kwargs
        super().__init__(model_name=model_name, api_key=resolved_api_key, temperature=temperature, **effective_kwargs)
        # self.pricing_model_name defaults to model_name. The get_model_pricing util handles variations like '-latest'.


    def _initialize_model(self) -> ChatGoogleGenerativeAI:
        """
        Initializes the LangChain `ChatGoogleGenerativeAI` instance.

        Returns:
            ChatGoogleGenerativeAI: The initialized LangChain client instance.

        Raises:
            ConfigurationError: If the API key is missing (and not in the environment).
            LLMInvocationError: If the ChatGoogleGenerativeAI client initialization fails.
        """
        logger.debug(f"Initializing ChatGoogleGenerativeAI for model: {self.model_name}")

        if not self.api_key:
            import os
            if not os.getenv("GOOGLE_API_KEY"):
                raise ConfigurationError("Google API key not provided and GOOGLE_API_KEY environment variable is not set.")
            logger.warning("Google API key not directly provided, relying on environment variable.")

        try:
            # LangChain uses 'model' parameter for ChatGoogleGenerativeAI
            chat_model = ChatGoogleGenerativeAI(
                model=self.model_name,
                google_api_key=self.api_key, # Pass None if relying on env var
                temperature=self.temperature,
                **self.additional_kwargs # Includes convert_system_message_to_human=True
            )
            logger.debug("ChatGoogleGenerativeAI instance created successfully.")
            return chat_model
        except Exception as e:
            logger.error(f"Failed to initialize ChatGoogleGenerativeAI for model '{self.model_name}': {e}", exc_info=True)
            raise LLMInvocationError(f"Failed to initialize Google GenAI client: {e}") from e


    def invoke(
        self,
        prompt: Union[str, List[Dict[str, str]], List[BaseMessage], ChatPromptValue]
    ) -> Any:
        """
        Invokes the initialized Gemini model with the provided prompt.

        Args:
            prompt: The input prompt (string, message dict list, BaseMessage list, or ChatPromptValue).

        Returns:
            Any: The raw response from `ChatGoogleGenerativeAI.invoke()`. This might be
                 an `AIMessage` or sometimes just a string depending on the model/version/prompt.

        Raises:
            LLMInvocationError: If the API call fails.
        """
        if self._model_instance is None:
             raise LLMInvocationError("Model instance is not initialized.")

        logger.debug(f"Invoking Gemini model '{self.model_name}' via LangChain wrapper.")
        try:
            response = self._model_instance.invoke(prompt)
            # Gemini response type can vary, log it
            logger.debug(f"Received response from Gemini model '{self.model_name}'. Type: {type(response)}")
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                 logger.trace(f"Gemini Usage Metadata received: {response.usage_metadata}")
            elif hasattr(response, 'response_metadata') and response.response_metadata.get('usage_metadata'): # Sometimes nested
                 logger.trace(f"Gemini Usage Metadata received (nested): {response.response_metadata['usage_metadata']}")

            # Return the raw response; parsing happens in the wrapper
            return response
        # Add specific Google error catching if desired
        # except ResourceExhausted as e: ...
        # except Unauthenticated as e: ...
        except Exception as e:
            logger.error(f"Error invoking Gemini model '{self.model_name}': {e}", exc_info=True)
            # Log specific details if available from Google errors
            # if hasattr(e, 'message'): logger.error(f"Google API Error Message: {e.message}")
            raise LLMInvocationError(f"Google GenAI API call failed: {e}") from e