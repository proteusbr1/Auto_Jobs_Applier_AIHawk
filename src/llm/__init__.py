# src/llm/__init__.py
"""
LLM package initialization.

Exports the main components for easy access.
"""

from .llm_processor import LLMProcessor
from .llm_manager import setup_llm_processor
from .interaction_logger import LoggingModelWrapper, log_interaction
from .adapter import AIAdapter, model_factory
from .models import AIModel # Export base class maybe?
from .exceptions import LLMError, APIKeyNotFoundError, ModelNotFoundError, ConfigurationError, LoggingError, LLMInvocationError, LLMParsingError

__all__ = [
    # Core Processor & Setup
    'LLMProcessor',
    'setup_llm_processor',

    # Logging & Wrapping
    'LoggingModelWrapper',
    'log_interaction', # Allow manual logging if needed

    # Lower-level components (optional to export all)
    'AIAdapter',
    'model_factory',
    'AIModel',

    # Exceptions
    'LLMError',
    'APIKeyNotFoundError',
    'ModelNotFoundError',
    'ConfigurationError',
    'LoggingError',
    'LLMInvocationError',
    'LLMParsingError',
]

# Configure Loguru logger for the LLM module if needed centrally
# from loguru import logger
# import sys
# logger.add(sys.stderr, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
# logger.add("logs/llm_module.log", rotation="10 MB", level="DEBUG") # Example file logging