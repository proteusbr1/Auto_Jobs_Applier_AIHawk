# src/llm/llm_manager.py
"""
Manages the creation and configuration of LLM processing components.

Provides functions to retrieve API keys securely and instantiate the
necessary classes (`AIAdapter`, `LoggingModelWrapper`, `LLMProcessor`)
based on application configuration.
"""

import os
from typing import Dict, Optional

from dotenv import load_dotenv
from loguru import logger

# Assuming LLMProcessor is the refactored version of LLMProcessor
from .llm_processor import LLMProcessor
from .adapter import AIAdapter, model_factory
from .interaction_logger import LoggingModelWrapper
from .exceptions import APIKeyNotFoundError, ConfigurationError, LLMError
from .config import DATA_OUTPUT_DIR, LLM_LOG_FILE_PATH # Import central config path

# Load environment variables from .env file if present
# Best practice: Load early in the application entry point, but including here for module self-containment example.
load_dotenv()

# Define expected environment variable names for API keys
API_KEY_ENV_VARS: Dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "huggingface": "HUGGINGFACEHUB_API_TOKEN", # Langchain uses HUGGINGFACEHUB_API_TOKEN
    # Add other provider keys here
    "ollama": "", # Ollama typically doesn't require a key
}


def get_api_key(llm_provider_type: str) -> Optional[str]:
    """
    Retrieves the API key for the specified LLM provider type from environment variables.

    Args:
        llm_provider_type (str): The type of LLM provider (e.g., "openai", "claude", "ollama").
                                 Should be lowercase.

    Returns:
        Optional[str]: The API key string if found, empty string for providers that don't need one (like Ollama),
                       or None if the provider type is unknown.

    Raises:
        APIKeyNotFoundError: If the key is expected but not found in environment variables.
    """
    provider_type_lower = llm_provider_type.lower()
    env_var_name = API_KEY_ENV_VARS.get(provider_type_lower)

    if env_var_name is None:
        logger.warning(f"API key environment variable mapping not found for provider type: '{llm_provider_type}'.")
        # Decide behavior: raise error or return None? Returning None for now.
        return None
    elif env_var_name == "": # Provider like Ollama doesn't need a key
        logger.debug(f"No API key required for provider type: '{llm_provider_type}'.")
        return "" # Return empty string to signal no key needed/found
    else:
        api_key = os.getenv(env_var_name)
        if not api_key:
            logger.error(f"API key environment variable '{env_var_name}' not set for provider '{llm_provider_type}'.")
            raise APIKeyNotFoundError(f"API key for '{llm_provider_type}' (env var: {env_var_name}) not found.")
        logger.debug(f"Successfully retrieved API key for provider: '{llm_provider_type}'.")
        # Consider returning only part of the key for security logs, e.g., f"{api_key[:4]}...{api_key[-4:]}"
        return api_key


def setup_llm_processor(
    app_config: Dict,
    resume_manager,
    salary_expectations: Optional[float] = None,
    min_score_to_apply: Optional[float] = None
) -> LLMProcessor:
    """
    Sets up and returns an initialized LLMProcessor instance.

    This function handles:
    1. Extracting LLM configuration from the main application config.
    2. Retrieving the necessary API key.
    3. Creating the specific AIModel instance using the factory.
    4. Wrapping the model instance with the logging wrapper.
    5. Initializing and returning the LLMProcessor with dependencies injected.

    Args:
        app_config (Dict): The main application configuration dictionary. Expected keys:
                           'llm_model_type', 'llm_model', 'llm_api_url' (optional).
        resume_manager: The resume manager instance containing the HTML resume.
        salary_expectations (Optional[float]): User's salary expectation.
        min_score_to_apply (Optional[float]): Minimum job score threshold.

    Returns:
        LLMProcessor: An initialized instance ready for use.

    Raises:
        ConfigurationError: If LLM configuration is missing or invalid.
        APIKeyNotFoundError: If the required API key is not found.
        ModelNotFoundError: If the specified model type is not supported.
        LLMError: For other LLM setup related errors.
    """
    logger.info("Setting up LLM Processor...")

    # --- 1. Get LLM Config ---
    llm_config = {
        'llm_model_type': app_config.get('llm_model_type'),
        'llm_model': app_config.get('llm_model'),
        'llm_api_url': app_config.get('llm_api_url'), # Optional
    }
    if not llm_config['llm_model_type'] or not llm_config['llm_model']:
        raise ConfigurationError("LLM config missing 'llm_model_type' or 'llm_model' in app_config.")

    # --- 2. Get API Key ---
    # API key retrieval can raise APIKeyNotFoundError
    api_key = get_api_key(llm_config['llm_model_type'])
    # Handle case where get_api_key returns None (unknown provider type)
    if api_key is None and llm_config['llm_model_type'].lower() not in API_KEY_ENV_VARS:
         raise ConfigurationError(f"Unknown LLM provider type '{llm_config['llm_model_type']}' encountered during API key retrieval.")


    # --- 3. Create AI Model Instance ---
    # model_factory can raise ModelNotFoundError, ConfigurationError, LLMInvocationError
    try:
        ai_model_instance = model_factory(config=llm_config, api_key=api_key)
    except LLMError as e: # Catch specific LLM errors from factory/init
        logger.error(f"Failed to create AI model instance: {e}", exc_info=True)
        raise # Re-raise the specific error
    except Exception as e: # Catch unexpected errors
        logger.error(f"Unexpected error creating AI model instance: {e}", exc_info=True)
        raise LLMError(f"Unexpected error during model creation: {e}") from e


    # --- 4. Wrap Model with Logging ---
    try:
        # Ensure the log directory exists (moved from config.py for clarity)
        LLM_LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        logged_model_wrapper = LoggingModelWrapper(
            model_instance=ai_model_instance,
            log_file_path=str(LLM_LOG_FILE_PATH) # Pass path as string
        )
    except (TypeError, Exception) as e:
        logger.error(f"Failed to initialize LoggingModelWrapper: {e}", exc_info=True)
        raise LLMError(f"Failed to setup logging wrapper: {e}") from e


    # --- 5. Initialize LLMProcessor ---
    try:
        # Get plain text content that was already extracted from HTML
        plain_text_content = resume_manager.get_plain_text_content()
        
        # Initialize LLMProcessor with the plain text content
        llm_processor = LLMProcessor(
            llm_wrapper=logged_model_wrapper,
            resume_content=plain_text_content,  # Now using plain text extracted by ResumeManager
            salary_expectations=salary_expectations,
            min_score_to_apply=min_score_to_apply
            # Pass other necessary configs if needed
        )
        logger.info("LLM Processor setup complete.")
        return llm_processor
    except (TypeError, ValueError, Exception) as e:
         logger.error(f"Failed to initialize LLMProcessor: {e}", exc_info=True)
         raise LLMError(f"Failed to initialize LLMProcessor: {e}") from e
