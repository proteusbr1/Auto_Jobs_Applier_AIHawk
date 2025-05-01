# src/llm/models/openai_model.py
"""
Concrete implementation of the AIModel interface for OpenAI models (GPT series).
Uses the `langchain-openai` package.
"""

from typing import Any, Union, List, Dict, Optional

from loguru import logger
# Ensure necessary LangChain components are imported
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage # For type hint
from langchain_core.prompt_values import ChatPromptValue # For type hint
# Import custom exceptions and base class
from .base_model import AIModel, LLMInvocationError, ConfigurationError
# Optionally import specific OpenAI exceptions if needed for finer error handling
# from openai import AuthenticationError, RateLimitError, APIConnectionError


class OpenAIModel(AIModel):
    """
    AIModel implementation for interacting with OpenAI's Chat models (like GPT-4o, GPT-3.5 Turbo).
    """

    def __init__(
        self,
        model_name: str,
        api_key: Optional[str] = None,
        temperature: Optional[float] = None,
        **kwargs: Any
    ):
        """
        Initializes the OpenAIModel.

        Args:
            model_name (str): The specific OpenAI model identifier (e.g., "gpt-4o", "gpt-3.5-turbo").
            api_key (Optional[str]): The OpenAI API key. If None, it attempts to use the
                                     `OPENAI_API_KEY` environment variable.
            temperature (Optional[float]): The sampling temperature. Defaults to `AIModel.DEFAULT_TEMPERATURE`.
            **kwargs: Additional keyword arguments passed directly to `ChatOpenAI`.
        """
        # Ensure api_key is resolved (either passed or from env) before calling super's _initialize_model
        resolved_api_key = api_key # Keep passed key separate if needed later
        super().__init__(model_name=model_name, api_key=resolved_api_key, temperature=temperature, **kwargs)
        # self.model_name is set in superclass
        # self.pricing_model_name defaults to model_name, which is usually correct for OpenAI


    def _initialize_model(self) -> ChatOpenAI:
        """
        Initializes the LangChain `ChatOpenAI` instance.

        Uses the `api_key`, `model_name`, `temperature`, and any additional kwargs
        provided during construction.

        Returns:
            ChatOpenAI: The initialized LangChain client instance.

        Raises:
            ConfigurationError: If the API key is missing (and not in the environment).
            LLMInvocationError: If the ChatOpenAI client initialization fails.
        """
        logger.debug(f"Initializing ChatOpenAI for model: {self.model_name}")

        # LangChain's ChatOpenAI automatically checks the environment variable if api_key is None.
        # However, explicitly checking can provide a clearer error message sooner.
        if not self.api_key:
             import os
             if not os.getenv("OPENAI_API_KEY"):
                    raise ConfigurationError("OpenAI API key not provided and OPENAI_API_KEY environment variable is not set.")
             logger.warning("OpenAI API key not directly provided, relying on environment variable.")
             # We pass None to ChatOpenAI, it will pick up from env
        try:
            # Pass relevant attributes to the LangChain model constructor
            chat_model = ChatOpenAI(
                model_name=self.model_name,
                openai_api_key=self.api_key, # Pass None if relying on env var
                temperature=self.temperature,
                **self.additional_kwargs # Pass any extra args like max_tokens, etc.
            )
            logger.debug("ChatOpenAI instance created successfully.")
            return chat_model
        # Catch potential specific errors during LangChain init if known, else general Exception
        except Exception as e:
            logger.error(f"Failed to initialize ChatOpenAI for model '{self.model_name}': {e}", exc_info=True)
            # Wrap in standard error type
            raise LLMInvocationError(f"Failed to initialize OpenAI client: {e}") from e


    def invoke(
        self,
        prompt: Union[str, List[Dict[str, str]], List[BaseMessage], ChatPromptValue]
    ) -> Any:
        """
        Invokes the initialized OpenAI model with the provided prompt.

        Args:
            prompt: The input prompt (string, message dict list, BaseMessage list, or ChatPromptValue).

        Returns:
            Any: The raw response from `ChatOpenAI.invoke()`, typically an `AIMessage` object.

        Raises:
            LLMInvocationError: If the API call fails (e.g., authentication, rate limit, network error).
        """
        if self._model_instance is None:
             raise LLMInvocationError("Model instance is not initialized.")

        logger.debug(f"Invoking OpenAI model '{self.model_name}' via LangChain wrapper.")
        try:
            # ChatOpenAI's invoke method handles various prompt types
            response = self._model_instance.invoke(prompt)
            logger.debug(f"Received response from OpenAI model '{self.model_name}'. Type: {type(response)}")
            # Log token usage if immediately available, though wrapper handles primary logging
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                 logger.trace(f"OpenAI Usage Metadata received: {response.usage_metadata}") # Use trace for verbose info
            return response # Return the raw response (usually AIMessage)
        # Add specific OpenAI error catching if desired
        # except AuthenticationError as e:
        #     logger.error(f"OpenAI Authentication Error: {e}", exc_info=True)
        #     raise LLMInvocationError(f"OpenAI Authentication Failed: {e}") from e
        # except RateLimitError as e:
        #     # Note: The wrapper handles retries for 429, but this might catch other rate limit scenarios
        #     logger.error(f"OpenAI Rate Limit Error: {e}", exc_info=True)
        #     raise LLMInvocationError(f"OpenAI Rate Limit Hit: {e}") from e
        # except APIConnectionError as e:
        #      logger.error(f"OpenAI Connection Error: {e}", exc_info=True)
        #      raise LLMInvocationError(f"OpenAI Connection Error: {e}") from e
        except Exception as e:
            # Catch other potential errors from LangChain or underlying httpx calls
            logger.error(f"Error invoking OpenAI model '{self.model_name}': {e}", exc_info=True)
            # Wrap in standard error type
            raise LLMInvocationError(f"OpenAI API call failed: {e}") from e