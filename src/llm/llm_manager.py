"""
Main module for managing LLM interactions.
This file serves as the main entry point for LLM functionality.
"""

import os
from dotenv import load_dotenv
from loguru import logger

from src.llm.gpt_answerer import GPTAnswerer

# Load environment variables
load_dotenv()


def get_api_key(llm_model_type: str) -> str:
    """
    Get the API key for the specified LLM model type.

    Args:
        llm_model_type (str): The type of LLM model (openai, claude, gemini, huggingface).

    Returns:
        str: The API key for the specified model type.

    Raises:
        ValueError: If the API key for the specified model type is not found.
    """
    api_key_map = {
        "openai": "OPENAI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "gemini": "GOOGLE_API_KEY",
        "huggingface": "HUGGINGFACE_API_KEY",
    }

    env_var = api_key_map.get(llm_model_type)
    if not env_var:
        logger.error(f"Unknown LLM model type: {llm_model_type}")
        raise ValueError(f"Unknown LLM model type: {llm_model_type}")

    api_key = os.getenv(env_var)
    if not api_key:
        logger.error(f"API key for {llm_model_type} not found in environment variables")
        raise ValueError(f"API key for {llm_model_type} not found in environment variables")

    return api_key


def create_gpt_answerer(config: dict) -> GPTAnswerer:
    """
    Create a GPTAnswerer instance with the specified configuration.

    Args:
        config (dict): Configuration dictionary containing model details.

    Returns:
        GPTAnswerer: An instance of GPTAnswerer.

    Raises:
        ValueError: If the model type is not supported or the API key is not found.
    """
    llm_model_type = config.get('llm_model_type')
    
    # For Ollama, we don't need an API key
    if llm_model_type == "ollama":
        api_key = ""
    else:
        api_key = get_api_key(llm_model_type)
    
    logger.debug(f"Creating GPTAnswerer with model type: {llm_model_type}")
    return GPTAnswerer(config, api_key)
