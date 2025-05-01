# src/llm/models/base_model.py
"""
Defines the Abstract Base Class (ABC) for all AI model interactions.

This ensures a consistent interface for different LLM providers, handling
common initialization attributes and defining the core `invoke` method signature.
"""

from abc import ABC, abstractmethod
from typing import Any, Union, List, Dict, Optional

from loguru import logger
from langchain_core.messages import BaseMessage # For type hinting prompt lists
from langchain_core.prompt_values import ChatPromptValue # For type hinting

# Import custom exceptions
from ..exceptions import LLMInvocationError, ConfigurationError


class AIModel(ABC):
    """
    Abstract base class for concrete AI model implementations.

    Provides a common structure for initialization and interaction. Subclasses
    must implement `_initialize_model` for provider-specific setup and `invoke`
    to interact with the model's API.
    """

    DEFAULT_TEMPERATURE = 0.1 # Default temperature for more deterministic output

    def __init__(
        self,
        model_name: str,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        temperature: Optional[float] = None,
        **kwargs: Any # Allow additional provider-specific kwargs
    ):
        """
        Initializes the base AI model attributes.

        Args:
            model_name (str): The specific name or identifier of the model to use
                              (e.g., "gpt-4o", "claude-3-opus-20240229").
            api_key (Optional[str]): The API key for the LLM service. Not required for
                                     all providers (e.g., local Ollama).
            api_url (Optional[str]): The base URL for the API endpoint. Useful for
                                     self-hosted or non-standard endpoints (e.g., Ollama).
            temperature (Optional[float]): The sampling temperature for generation.
                                           Lower values (e.g., 0.1) are more deterministic.
                                           Defaults to DEFAULT_TEMPERATURE.
            **kwargs: Additional keyword arguments specific to the underlying model provider.
        """
        if not model_name or not isinstance(model_name, str):
            raise ConfigurationError("`model_name` must be a non-empty string.")

        self.model_name: str = model_name
        # pricing_model_name defaults to model_name, can be overridden by subclass if needed
        # (e.g., if pricing tiers use different names). The get_model_pricing util handles most variations.
        self.pricing_model_name: str = model_name
        self.api_key: Optional[str] = api_key
        self.api_url: Optional[str] = api_url
        self.temperature: float = temperature if temperature is not None else self.DEFAULT_TEMPERATURE
        self.additional_kwargs: Dict[str, Any] = kwargs # Store extra args

        # Placeholder for the initialized client instance (set in _initialize_model)
        self._model_instance: Any = None

        # Call the subclass implementation to initialize the actual client
        try:
             self._model_instance = self._initialize_model()
             if self._model_instance is None:
                  # Ensure _initialize_model returns something or raises an error
                  raise LLMInvocationError(f"Model initialization for {self.__class__.__name__} returned None.")
             logger.info(f"Initialized AIModel: {self.__class__.__name__} with model_name: {self.model_name}")
        except Exception as e:
             # Catch any error during subclass initialization
             logger.error(f"Failed during initialization of {self.__class__.__name__} for model {self.model_name}: {e}", exc_info=True)
             # Re-raise as a standard error type, preserving the original cause
             if isinstance(e, (ConfigurationError, LLMInvocationError)):
                 raise # Keep specific errors
             else:
                 raise LLMInvocationError(f"Initialization failed for {self.model_name}: {e}") from e


    @abstractmethod
    def _initialize_model(self) -> Any:
        """
        Provider-specific method to initialize the underlying LLM client/instance.

        This method should use `self.model_name`, `self.api_key`, `self.api_url`,
        `self.temperature`, and `self.additional_kwargs` as needed to configure
        and return the actual object used for making API calls (e.g., a LangChain
        ChatModel instance).

        Returns:
            The initialized model client instance (e.g., ChatOpenAI, ChatAnthropic).

        Raises:
            ConfigurationError: If required configuration (like API key) is missing.
            LLMInvocationError: If the client initialization fails (e.g., invalid key, connection error).
        """
        pass

    @abstractmethod
    def invoke(
        self,
        prompt: Union[str, List[Dict[str, str]], List[BaseMessage], ChatPromptValue]
    ) -> Any:
        """
        Sends a prompt to the configured AI model and returns the raw response.

        The prompt format flexibility allows compatibility with various LangChain
        components and direct string inputs. Subclasses must implement the logic
        to call the underlying model's API correctly based on the input type if necessary.

        Args:
            prompt: The input prompt. Can be a simple string, a list of message
                    dictionaries (e.g., `[{"role": "user", "content": "..."}]`),
                    a list of LangChain `BaseMessage` objects, or a `ChatPromptValue`.

        Returns:
            Any: The raw response object from the underlying model's invocation.
                 The exact type (e.g., AIMessage, str, dict) depends on the provider
                 and LangChain integration. This raw response will be parsed later
                 by the `LoggingModelWrapper`.

        Raises:
            LLMInvocationError: If the API call fails (e.g., network error, authentication
                                error, rate limit after retries handled by wrapper).
        """
        pass

    def get_model_name(self) -> str:
        """Returns the configured model name used for initialization."""
        return self.model_name

    def get_pricing_model_name(self) -> str:
        """
        Returns the model name intended for pricing lookups.
        Defaults to `model_name` but can be overridden by subclasses if needed.
        """
        return self.pricing_model_name