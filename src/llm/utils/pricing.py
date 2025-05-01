# src/llm/utils/pricing.py
"""
Provides pricing information for various Large Language Models (LLMs).

This module centralizes the cost per token for different models, facilitating
cost calculation for LLM interactions. Prices are typically based on millions of tokens.

Sources:
- OpenAI: https://platform.openai.com/docs/pricing
- Google AI: https://ai.google.dev/gemini-api/docs/pricing
- Anthropic: https://www.anthropic.com/pricing#api

Note: Prices are subject to change by the providers. Last check suggested around late 2024/early 2025.
All prices are in USD per 1,000,000 tokens unless otherwise specified.
"""

from typing import Dict, Final
from loguru import logger

# --- Constants for Default Pricing ---
# Using gpt-4o-mini pricing as a reasonable default if a model isn't listed.
DEFAULT_INPUT_TOKEN_PRICE: Final[float] = 0.15 / 1_000_000  # $0.15 per 1M input tokens
DEFAULT_OUTPUT_TOKEN_PRICE: Final[float] = 0.60 / 1_000_000 # $0.60 per 1M output tokens

# --- Model Pricing Dictionary ---
# Keys should be the exact model names used in API calls or configuration.
# Structure: { "model_name": {"input_token_price": float, "output_token_price": float} }
MODEL_PRICING: Final[Dict[str, Dict[str, float]]] = {
    "gemini-1.5-flash-8b": {
        "input_token_price": 0.0375 / 1_000_000, # Preço para prompts <= 128k tokens
        "output_token_price": 0.15 / 1_000_000,  # Preço para prompts <= 128k tokens
    },
    "gemini-2.0-flash-lite": {
        "input_token_price": 0.075 / 1_000_000,
        "output_token_price": 0.30 / 1_000_000,
    },
    "gemini-1.5-flash": {
        "input_token_price": 0.075 / 1_000_000, # Preço para prompts <= 128k tokens
        "output_token_price": 0.30 / 1_000_000,  # Preço para prompts <= 128k tokens
    },
    "gpt-4.1-nano-2025-04-14": {
        "input_token_price": 0.10 / 1_000_000,
        "output_token_price": 0.40 / 1_000_000,
    },
    "gemini-2.0-flash": {
        "input_token_price": 0.10 / 1_000_000, # Preço para texto/imagem/vídeo. Áudio: $0.70
        "output_token_price": 0.40 / 1_000_000,
    },
    "gpt-4o-mini": {
        "input_token_price": 0.15 / 1_000_000,
        "output_token_price": 0.60 / 1_000_000,
    },
    "gpt-4o-mini-2024-07-18": {
        "input_token_price": 0.15 / 1_000_000,
        "output_token_price": 0.60 / 1_000_000,
    },
    "gpt-4o-mini-audio-preview-2024-12-17": {
        "input_token_price": 0.15 / 1_000_000, # Preço de token de texto inferido, o áudio é diferente
        "output_token_price": 0.60 / 1_000_000,
    },
    "gpt-4o-mini-search-preview-2025-03-11": {
        "input_token_price": 0.15 / 1_000_000,
        "output_token_price": 0.60 / 1_000_000,
    },
    "gemini-2.5-flash-preview-04-17": {
        "input_token_price": 0.15 / 1_000_000, # Preço para texto/imagem/vídeo. Áudio: $1.00
        "output_token_price": 0.60 / 1_000_000, # Preço para non-thinking. Thinking: $3.50
    },
    "grok-3-mini-beta": {
        "input_token_price": 0.30 / 1_000_000, # Preço para texto/imagem/vídeo. Áudio: $1.00
        "output_token_price": 0.50 / 1_000_000, # Preço para non-thinking. Thinking: $3.50
    },
    "gpt-4.1-mini-2025-04-14": {
        "input_token_price": 0.40 / 1_000_000,
        "output_token_price": 1.60 / 1_000_000,
    },
    "gpt-4o-mini-realtime-preview-2024-12-17": {
        "input_token_price": 0.60 / 1_000_000,
        "output_token_price": 2.40 / 1_000_000,
    },
    "claude-3-5-haiku-latest": {
        "input_token_price": 0.80 / 1_000_000,
        "output_token_price": 4.00 / 1_000_000,
    },
    "o4-mini-2025-04-16": {
        "input_token_price": 1.10 / 1_000_000,
        "output_token_price": 4.40 / 1_000_000,
    },
    "o3-mini-2025-01-31": {
        "input_token_price": 1.10 / 1_000_000,
        "output_token_price": 4.40 / 1_000_000,
    },
    "o1-mini": {
        "input_token_price": 1.10 / 1_000_000,
        "output_token_price": 4.40 / 1_000_000,
    },
    "o1-mini-2024-09-12": {
        "input_token_price": 1.10 / 1_000_000,
        "output_token_price": 4.40 / 1_000_000,
    },
    "gemini-1.5-pro": {
        "input_token_price": 1.25 / 1_000_000, # Preço para prompts <= 128k tokens
        "output_token_price": 5.00 / 1_000_000,  # Preço para prompts <= 128k tokens
    },
    "gemini-2.5-pro-preview": {
        "input_token_price": 1.25 / 1_000_000, # Preço para prompts <= 200k tokens
        "output_token_price": 10.00 / 1_000_000, # Preço para prompts <= 200k tokens (inclui thinking tokens)
    },
    "gpt-4.1-2025-04-14": {
        "input_token_price": 2.00 / 1_000_000,
        "output_token_price": 8.00 / 1_000_000,
    },
    "gpt-4o": {
        "input_token_price": 2.50 / 1_000_000,
        "output_token_price": 10.00 / 1_000_000,
    },
    "gpt-4o-2024-08-06": {
        "input_token_price": 2.50 / 1_000_000,
        "output_token_price": 10.00 / 1_000_000,
    },
    "gpt-4o-audio-preview-2024-12-17": {
        "input_token_price": 2.50 / 1_000_000, # Preço de token de texto inferido, o áudio é diferente
        "output_token_price": 10.00 / 1_000_000,
    },
    "gpt-4o-search-preview-2025-03-11": {
        "input_token_price": 2.50 / 1_000_000,
        "output_token_price": 10.00 / 1_000_000,
    },
    "computer-use-preview-2025-03-11": {
        "input_token_price": 3.00 / 1_000_000,
        "output_token_price": 12.00 / 1_000_000,
    },
    "claude-3-7-sonnet-latest": {
        "input_token_price": 3.00 / 1_000_000,
        "output_token_price": 15.00 / 1_000_000,
    },
    "grok-3-beta": {
        "input_token_price": 3.00 / 1_000_000,
        "output_token_price": 15.00 / 1_000_000,
    },
    "gpt-4o-realtime-preview-2024-12-17": {
        "input_token_price": 5.00 / 1_000_000,
        "output_token_price": 20.00 / 1_000_000,
    },
    "gpt-image-1": {
        "input_token_price": 5.00 / 1_000_000, # Preço por imagem, não diretamente comparável a tokens
        "output_token_price": 0.0 / 1_000_000,
    },
    "o3-2025-04-16": {
        "input_token_price": 10.00 / 1_000_000,
        "output_token_price": 40.00 / 1_000_000,
    },
    "o1-2024-12-17": {
        "input_token_price": 15.00 / 1_000_000,
        "output_token_price": 60.00 / 1_000_000,
    },
    "gpt-4.5-preview-2025-02-27": {
        "input_token_price": 75.00 / 1_000_000,
        "output_token_price": 150.00 / 1_000_000,
    },
    "o1-pro-2025-03-19": {
        "input_token_price": 150.00 / 1_000_000,
        "output_token_price": 600.00 / 1_000_000,
    },
}


def get_model_pricing(model_name: str) -> Dict[str, float]:
    """
    Retrieves the input and output token pricing for a given model name.

    Performs case-insensitive matching and checks if the provided name starts
    with a known base model name. Falls back to default prices if no match is found.

    Args:
        model_name (str): The name of the LLM (e.g., "gpt-4o", "claude-3-5-sonnet-20240620").

    Returns:
        Dict[str, float]: A dictionary containing 'input_token_price' and 'output_token_price'.
    """
    if not model_name or not isinstance(model_name, str):
        logger.warning("Invalid model name provided for pricing lookup. Using default pricing.")
        return {
            "input_token_price": DEFAULT_INPUT_TOKEN_PRICE,
            "output_token_price": DEFAULT_OUTPUT_TOKEN_PRICE,
        }

    # 1. Try exact match (case-sensitive, assumes keys in MODEL_PRICING are canonical)
    if model_name in MODEL_PRICING:
        logger.debug(f"Found exact pricing match for model: {model_name}")
        return MODEL_PRICING[model_name]

    # 2. Try case-insensitive match
    model_name_lower = model_name.lower()
    for known_model, prices in MODEL_PRICING.items():
        if known_model.lower() == model_name_lower:
            logger.debug(f"Found case-insensitive pricing match for model: {model_name} -> {known_model}")
            return prices

    # 3. Try prefix match (e.g., "gpt-4-turbo-preview" should match "gpt-4-turbo")
    #    Sort known models by length descending to match longest prefix first (e.g. gpt-4o-mini before gpt-4o)
    sorted_known_models = sorted(MODEL_PRICING.keys(), key=len, reverse=True)
    for base_model in sorted_known_models:
        if model_name.startswith(base_model):
            logger.debug(f"Found prefix pricing match for model: {model_name} -> {base_model}")
            return MODEL_PRICING[base_model]

    # 4. Fallback to default pricing
    logger.warning(f"Pricing not found for model: '{model_name}'. Using default pricing.")
    return {
        "input_token_price": DEFAULT_INPUT_TOKEN_PRICE,
        "output_token_price": DEFAULT_OUTPUT_TOKEN_PRICE,
    }