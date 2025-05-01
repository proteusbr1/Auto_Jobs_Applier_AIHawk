# src/llm/models/__init__.py
"""
Models package initialization.

Exports the base AIModel class and all concrete model implementations
for different LLM providers (OpenAI, Anthropic Claude, Google Gemini,
Ollama, Hugging Face).
"""

# Base class
from .base_model import AIModel

# Concrete implementations
from .openai_model import OpenAIModel
from .claude_model import ClaudeModel
from .ollama_model import OllamaModel
from .gemini_model import GeminiModel
from .huggingface_model import HuggingFaceModel

# Define what gets imported when using 'from src.llm.models import *'
# Also useful for static analysis tools.
__all__ = [
    # Base Class
    'AIModel',
    # Concrete Implementations
    'OpenAIModel',
    'ClaudeModel',
    'OllamaModel',
    'GeminiModel',
    'HuggingFaceModel',
]