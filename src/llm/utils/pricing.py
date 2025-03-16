"""
Pricing information for different AI models.
"""

# https://openai.com/api/pricing/
MODEL_PRICING = {
    "gpt-4o": {
        "input_token_price": 2.50 / 1_000_000, 
        "output_token_price": 10.00 / 1_000_000, 
    },
    "gpt-4o-2024-08-06": {
        "input_token_price": 2.50 / 1_000_000,
        "output_token_price": 10.00 / 1_000_000,
    },
    "gpt-4o-audio-preview": {
        "input_token_price": 2.50 / 1_000_000,
        "output_token_price": 10.00 / 1_000_000,
    },
    "gpt-4o-audio-preview-2024-10-01": {
        "input_token_price": 2.50 / 1_000_000,
        "output_token_price": 10.00 / 1_000_000,
    },
    "gpt-4o-2024-05-13": {
        "input_token_price": 5.00 / 1_000_000,
        "output_token_price": 15.00 / 1_000_000,
    },
    "gpt-4o-mini": {
        "input_token_price": 0.150 / 1_000_000,
        "output_token_price": 0.600 / 1_000_000,
    },
    "gpt-4o-mini-2024-07-18": {
        "input_token_price": 0.150 / 1_000_000,
        "output_token_price": 0.600 / 1_000_000,
    },
    "o1-preview": {
        "input_token_price": 15.00 / 1_000_000,
        "output_token_price": 60.00 / 1_000_000,
    },
    "o1-preview-2024-09-12": {
        "input_token_price": 15.00 / 1_000_000,
        "output_token_price": 60.00 / 1_000_000,
    },
    "o1-mini": {
        "input_token_price": 3.00 / 1_000_000,
        "output_token_price": 12.00 / 1_000_000,
    },
    "o1-mini-2024-09-12": {
        "input_token_price": 3.00 / 1_000_000,
        "output_token_price": 12.00 / 1_000_000,
    },
}
