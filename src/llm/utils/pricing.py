"""
Pricing information for different AI models.
"""

from typing import Dict

# https://platform.openai.com/docs/pricing
# https://ai.google.dev/gemini-api/docs/pricing
# https://www.anthropic.com/pricing#api
MODEL_PRICING = {
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

# Default prices for unknown models
DEFAULT_INPUT_TOKEN_PRICE = 0.15 / 1_000_000   # $0.15 per 1000000 tokens
DEFAULT_OUTPUT_TOKEN_PRICE = 0.60 / 1_000_000  # $0.60 per 1000000 tokens

def get_model_pricing(model_name: str) -> Dict[str, float]:
    """
    Get the pricing information for a specific model.
    
    Args:
        model_name (str): The name of the model.
        
    Returns:
        Dict[str, float]: A dictionary containing the pricing information.
    """
    # Try exact match first
    if model_name in MODEL_PRICING:
        return MODEL_PRICING[model_name]
    
    # Try lowercase match
    model_name_lower = model_name.lower()
    if model_name_lower in MODEL_PRICING:
        return MODEL_PRICING[model_name_lower]
    
    # For API models with suffixes, try to match the base model name
    for base_model in MODEL_PRICING:
        if model_name.startswith(base_model):
            return MODEL_PRICING[base_model]
    
    # Return default pricing if no match is found
    return {
        "input_token_price": DEFAULT_INPUT_TOKEN_PRICE,
        "output_token_price": DEFAULT_OUTPUT_TOKEN_PRICE
    }
