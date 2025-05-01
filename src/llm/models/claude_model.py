# src/llm/models/claude_model.py
"""
Concrete implementation of the AIModel interface for Anthropic Claude models.
Uses the `langchain-anthropic` package.
"""

from typing import Any, Union, List, Dict, Optional

from loguru import logger
# Ensure necessary LangChain components are imported
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage # For type hint
from langchain_core.prompt_values import ChatPromptValue # For type hint
# Import custom exceptions and base class
from .base_model import AIModel, LLMInvocationError, ConfigurationError
# Optionally import specific Anthropic exceptions if needed
# from anthropic import AuthenticationError, RateLimitError, APIConnectionError


class ClaudeModel(AIModel):
    """
    AIModel implementation for interacting with Anthropic's Claude models.
    """

    def __init__(
        self,
        model_name: str,
        api_key: Optional[str] = None,
        temperature: Optional[float] = None,
        **kwargs: Any
    ):
        """
        Initializes the ClaudeModel.

        Args:
            model_name (str): The specific Claude model identifier (e.g., "claude-3-opus-20240229").
            api_key (Optional[str]): The Anthropic API key. If None, it attempts to use the
                                     `ANTHROPIC_API_KEY` environment variable.
            temperature (Optional[float]): The sampling temperature. Defaults to `AIModel.DEFAULT_TEMPERATURE`.
            **kwargs: Additional keyword arguments passed directly to `ChatAnthropic`.
        """
        resolved_api_key = api_key
        super().__init__(model_name=model_name, api_key=resolved_api_key, temperature=temperature, **kwargs)
        # self.pricing_model_name defaults to model_name, usually correct for Claude


    def _initialize_model(self) -> ChatAnthropic:
        """
        Initializes the LangChain `ChatAnthropic` instance.

        Returns:
            ChatAnthropic: The initialized LangChain client instance.

        Raises:
            ConfigurationError: If the API key is missing (and not in the environment).
            LLMInvocationError: If the ChatAnthropic client initialization fails.
        """
        logger.debug(f"Initializing ChatAnthropic for model: {self.model_name}")

        if not self.api_key:
            import os
            if not os.getenv("ANTHROPIC_API_KEY"):
                raise ConfigurationError("Anthropic API key not provided and ANTHROPIC_API_KEY environment variable is not set.")
            logger.warning("Anthropic API key not directly provided, relying on environment variable.")

        try:
            # LangChain uses 'model' parameter for ChatAnthropic constructor
            chat_model = ChatAnthropic(
                model=self.model_name,
                anthropic_api_key=self.api_key, # Pass None if relying on env var
                temperature=self.temperature,
                **self.additional_kwargs
            )
            logger.debug("ChatAnthropic instance created successfully.")
            return chat_model
        except Exception as e:
            logger.error(f"Failed to initialize ChatAnthropic for model '{self.model_name}': {e}", exc_info=True)
            raise LLMInvocationError(f"Failed to initialize Anthropic client: {e}") from e


    def invoke(
        self,
        prompt: Union[str, List[Dict[str, str]], List[BaseMessage], ChatPromptValue]
    ) -> Any:
        """
        Invokes the initialized Claude model with the provided prompt.

        Args:
            prompt: The input prompt (string, message dict list, BaseMessage list, or ChatPromptValue).

        Returns:
            Any: The raw response from `ChatAnthropic.invoke()`, typically an `AIMessage` object.

        Raises:
            LLMInvocationError: If the API call fails.
        """
        if self._model_instance is None:
             raise LLMInvocationError("Model instance is not initialized.")

        logger.debug(f"Invoking Claude model '{self.model_name}' via LangChain wrapper.")
        try:
            response = self._model_instance.invoke(prompt)
            logger.debug(f"Received response from Claude model '{self.model_name}'. Type: {type(response)}")
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                 logger.trace(f"Claude Usage Metadata received: {response.usage_metadata}")
            return response
        # Add specific Anthropic error catching if desired
        # except AuthenticationError as e: ...
        except Exception as e:
            logger.error(f"Error invoking Claude model '{self.model_name}': {e}", exc_info=True)
            raise LLMInvocationError(f"Anthropic API call failed: {e}") from e