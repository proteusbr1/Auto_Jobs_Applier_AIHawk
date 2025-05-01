# src/llm/models/ollama_model.py
"""
Concrete implementation of the AIModel interface for locally running Ollama models.
Uses the `langchain-ollama` package (or `langchain-community` if using older versions).
"""

from typing import Any, Union, List, Dict, Optional

from loguru import logger
# Use the appropriate import based on langchain version
try:
    from langchain_ollama import ChatOllama
except ImportError:
    from langchain_community.chat_models import ChatOllama # Fallback for older langchain

from langchain_core.messages import BaseMessage # For type hint
from langchain_core.prompt_values import ChatPromptValue # For type hint
# Import custom exceptions and base class
from .base_model import AIModel, LLMInvocationError, ConfigurationError


class OllamaModel(AIModel):
    """
    AIModel implementation for interacting with models served by Ollama.
    """
    DEFAULT_OLLAMA_URL = "http://localhost:11434"

    def __init__(
        self,
        model_name: str,
        api_url: Optional[str] = None, # Ollama uses api_url, not api_key
        temperature: Optional[float] = None,
        **kwargs: Any
    ):
        """
        Initializes the OllamaModel.

        Args:
            model_name (str): The name of the Ollama model to use (e.g., "llama3", "mistral").
            api_url (Optional[str]): The base URL of the Ollama server. Defaults to
                                     `http://localhost:11434`.
            temperature (Optional[float]): The sampling temperature. Defaults to `AIModel.DEFAULT_TEMPERATURE`.
            **kwargs: Additional keyword arguments passed directly to `ChatOllama`.
        """
        # Ollama doesn't use an API key in the traditional sense
        # Pass api_url, model_name, temperature to super
        effective_api_url = api_url or self.DEFAULT_OLLAMA_URL
        super().__init__(model_name=model_name, api_key=None, api_url=effective_api_url, temperature=temperature, **kwargs)
        # Distinguish pricing name for clarity, though price is usually 0
        self.pricing_model_name = f"ollama/{model_name}"


    def _initialize_model(self) -> ChatOllama:
        """
        Initializes the LangChain `ChatOllama` instance.

        Uses the `model_name`, `api_url`, `temperature`, and any additional kwargs.

        Returns:
            ChatOllama: The initialized LangChain client instance.

        Raises:
            LLMInvocationError: If the ChatOllama client initialization or connection fails.
        """
        logger.debug(f"Initializing ChatOllama for model: {self.model_name} at URL: {self.api_url}")

        try:
            # Pass relevant attributes to the LangChain model constructor
            # Check Langchain docs for exact parameter names if needed (`base_url`)
            chat_model = ChatOllama(
                model=self.model_name,
                base_url=self.api_url,
                temperature=self.temperature,
                **self.additional_kwargs
            )
            # Test connection? ChatOllama might do this lazily.
            # Consider adding a small test invoke here or rely on first invoke call.
            logger.debug("ChatOllama instance created successfully.")
            return chat_model
        except Exception as e:
            logger.error(f"Failed to initialize ChatOllama for model '{self.model_name}' at {self.api_url}: {e}", exc_info=True)
            raise LLMInvocationError(f"Failed to initialize Ollama client/connection: {e}") from e


    def invoke(
        self,
        prompt: Union[str, List[Dict[str, str]], List[BaseMessage], ChatPromptValue]
    ) -> Any:
        """
        Invokes the initialized Ollama model with the provided prompt.

        Args:
            prompt: The input prompt (string, message dict list, BaseMessage list, or ChatPromptValue).

        Returns:
            Any: The raw response from `ChatOllama.invoke()`, typically an `AIMessage`.

        Raises:
            LLMInvocationError: If the call to the Ollama server fails.
        """
        if self._model_instance is None:
             raise LLMInvocationError("Model instance is not initialized.")

        logger.debug(f"Invoking Ollama model '{self.model_name}' at {self.api_url}")
        try:
            # ChatOllama should handle different prompt types
            response = self._model_instance.invoke(prompt)
            logger.debug(f"Received response from Ollama model '{self.model_name}'. Type: {type(response)}")
            # Ollama responses via Langchain usually have AIMessage structure but might lack usage metadata
            if hasattr(response, 'response_metadata') and response.response_metadata:
                 logger.trace(f"Ollama Response Metadata received: {response.response_metadata}")
            return response
        except Exception as e:
            # Catch potential connection errors or Ollama server errors
            logger.error(f"Error invoking Ollama model '{self.model_name}': {e}", exc_info=True)
            # Check for connection refused type errors?
            # import httpx
            # if isinstance(e, httpx.ConnectError): raise LLMInvocationError(...)
            raise LLMInvocationError(f"Ollama API call failed: {e}") from e