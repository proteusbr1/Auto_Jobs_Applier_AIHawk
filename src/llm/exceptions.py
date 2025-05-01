# src/llm/exceptions.py
"""
Custom exceptions for the LLM module.
"""

class LLMError(Exception):
    """Base exception for LLM module errors."""
    pass

class APIKeyNotFoundError(LLMError):
    """Raised when an API key is not found."""
    pass

class ModelNotFoundError(LLMError):
    """Raised when a specified model is not supported or found."""
    pass

class LLMInvocationError(LLMError):
    """Raised when invoking the LLM fails."""
    pass

class LLMParsingError(LLMError):
    """Raised when parsing the LLM response fails."""
    pass

class ConfigurationError(LLMError):
    """Raised for LLM configuration issues."""
    pass

class LoggingError(LLMError):
    """Raised for errors during LLM interaction logging."""
    pass