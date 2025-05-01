# src/llm/adapter.py
"""
Adapter and Factory for creating and interacting with different AI model implementations.

This module acts as a bridge between the application logic and the specific
LLM implementations defined in `models.py`. It uses a factory pattern
to instantiate the correct model based on configuration.
"""

from typing import Dict, Type

from loguru import logger

from .models import (
    AIModel,
    OpenAIModel,
    ClaudeModel,
    OllamaModel,
    GeminiModel,
    HuggingFaceModel
)
from .exceptions import ModelNotFoundError, ConfigurationError, LLMInvocationError


class AIAdapter:
    """
    Adapter class that wraps a specific AIModel instance.

    It delegates the `invoke` call to the underlying model instance.
    This provides a consistent interface regardless of the chosen LLM provider.
    """

    def __init__(self, model_instance: AIModel):
        """
        Initializes the AIAdapter with a specific AIModel instance.

        Args:
            model_instance (AIModel): An initialized instance of a concrete AIModel subclass
                                      (e.g., OpenAIModel, ClaudeModel).

        Raises:
            TypeError: If `model_instance` is not a subclass of AIModel.
        """
        if not isinstance(model_instance, AIModel):
            raise TypeError(f"model_instance must be an instance of AIModel, not {type(model_instance)}")
        self._model = model_instance
        logger.info(f"AIAdapter initialized with model: {self._model.__class__.__name__} ({self._model.get_model_name()})")

    def invoke(self, prompt: any) -> any:
        """
        Invokes the underlying AI model with the given prompt.

        Args:
            prompt (any): The input prompt suitable for the underlying model's invoke method.

        Returns:
            any: The response from the AI model (structure depends on the model).

        Raises:
            LLMInvocationError: If the underlying model invocation fails.
        """
        logger.debug(f"AIAdapter invoking underlying model: {self._model.__class__.__name__}")
        try:
            # Delegate the call to the specific model implementation
            return self._model.invoke(prompt)
        except LLMInvocationError:
             # Re-raise specific LLM errors directly
             raise
        except Exception as e:
            # Catch any other unexpected errors during invocation
            logger.error(f"Unexpected error during AIAdapter invoke for {self._model.__class__.__name__}: {e}", exc_info=True)
            # Wrap in a standard error type
            raise LLMInvocationError(f"Adapter failed to invoke model {self._model.get_model_name()}: {e}") from e

    @property
    def model(self) -> AIModel:
        """Provides access to the underlying AIModel instance."""
        return self._model


def model_factory(config: Dict[str, str], api_key: str) -> AIModel:
    """
    Factory function to create an instance of the appropriate AIModel based on configuration.

    Args:
        config (Dict[str, str]): Configuration dictionary containing required model details:
            'llm_model_type' (str): The type of the model (e.g., "openai", "claude", "ollama").
            'llm_model' (str): The specific model name (e.g., "gpt-4o", "llama3").
            'llm_api_url' (str, optional): The API base URL (primarily for Ollama/self-hosted).
        api_key (str): The API key for the selected AI model (can be empty for local models like Ollama).

    Returns:
        AIModel: An initialized instance of a concrete AIModel subclass.

    Raises:
        ConfigurationError: If required configuration keys are missing.
        ModelNotFoundError: If the `llm_model_type` is unsupported.
        LLMInvocationError: If model initialization fails (e.g., invalid key, connection error).
    """
    llm_model_type = config.get('llm_model_type')
    llm_model_name = config.get('llm_model')
    llm_api_url = config.get('llm_api_url') # Optional, defaults handled in model class

    if not llm_model_type or not llm_model_name:
        raise ConfigurationError("Missing required configuration: 'llm_model_type' and 'llm_model' must be provided.")

    # Map model types to their corresponding classes
    model_class_map: Dict[str, Type[AIModel]] = {
        "openai": OpenAIModel,
        "claude": ClaudeModel,
        "ollama": OllamaModel,
        "gemini": GeminiModel,
        "huggingface": HuggingFaceModel,
        # Add other model types here
    }

    logger.info(f"Attempting to create model: type='{llm_model_type}', name='{llm_model_name}', url='{llm_api_url or 'N/A'}'")

    model_class = model_class_map.get(llm_model_type.lower()) # Use lowercase for robustness

    if not model_class:
        logger.error(f"Unsupported LLM model type specified: {llm_model_type}")
        raise ModelNotFoundError(f"Unsupported model type: {llm_model_type}")

    try:
        # Instantiate the appropriate model class
        # Handle Ollama specifically as it might not need an API key but needs URL
        if model_class is OllamaModel:
             # Pass only necessary args for Ollama
            instance = model_class(model_name=llm_model_name, api_url=llm_api_url)
        else:
            # Other models generally need api_key and model_name
            instance = model_class(api_key=api_key, model_name=llm_model_name, api_url=llm_api_url) # Pass URL too, model can ignore if not needed

        logger.info(f"Successfully created model instance: {instance.__class__.__name__}")
        return instance
    except (ValueError, TypeError) as e: # Catch initialization errors like missing keys
        logger.error(f"Configuration error during model initialization for '{llm_model_type}': {e}", exc_info=True)
        raise ConfigurationError(f"Configuration error for {llm_model_type}: {e}") from e
    except LLMInvocationError: # Catch specific initialization errors from models
        logger.error(f"LLM Invocation error during model initialization for '{llm_model_type}'", exc_info=True)
        raise # Re-raise the specific error
    except Exception as e: # Catch unexpected initialization errors
        logger.error(f"Unexpected error creating model instance for '{llm_model_type}': {e}", exc_info=True)
        raise LLMInvocationError(f"Failed to create model instance {llm_model_name}: {e}") from e