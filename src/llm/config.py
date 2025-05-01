# src/llm/config.py
"""
Configuration settings for the LLM module.
Centralizes configurable parameters like paths and constants.
"""

import os
from pathlib import Path

# Define base directory if needed, assuming script is run from project root
# Or use environment variables for more flexibility
PROJECT_ROOT = Path(__file__).parent.parent.parent # Adjust as needed
DATA_OUTPUT_DIR = PROJECT_ROOT / "data_folder" / "output"
LOG_FILE_NAME = "llm_interactions.json"

# Ensure the output directory exists
DATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LLM_LOG_FILE_PATH = DATA_OUTPUT_DIR / LOG_FILE_NAME

# --- Default values (can be overridden by external config) ---
DEFAULT_MODEL_TYPE = "openai"
DEFAULT_MODEL_NAME = "gpt-4o-mini" # Example default

# Function to get config values, potentially integrating with a broader config system
def get_llm_config_value(key: str, default=None):
    """Retrieves a configuration value, potentially from environment or a config file."""
    # Example: prioritize environment variables
    value = os.getenv(f"LLM_{key.upper()}", default)
    # Add logic here to read from a config file (e.g., YAML, .env) if needed
    return value