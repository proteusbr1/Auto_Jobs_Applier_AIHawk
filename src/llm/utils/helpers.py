# src/llm/utils/helpers.py
"""
Utility functions for the LLM module.
"""
import re
import textwrap
from typing import List, Union, Dict, Optional
from datetime import datetime

from Levenshtein import distance as levenshtein_distance # Use specific name
from loguru import logger
from langchain_core.messages import BaseMessage
from langchain_core.prompt_values import StringPromptValue, ChatPromptValue

def find_best_match(text: str, options: List[str]) -> Optional[str]:
    """
    Find the best matching option from a list based on Levenshtein distance.

    Args:
        text (str): The text to match against the options.
        options (List[str]): A list of possible options.

    Returns:
        Optional[str]: The option that best matches the input text, or None if options are empty.

    Raises:
        TypeError: If input types are invalid.
    """
    if not isinstance(text, str):
        raise TypeError("Input 'text' must be a string.")
    if not isinstance(options, list) or not all(isinstance(opt, str) for opt in options):
        raise TypeError("Input 'options' must be a list of strings.")
    if not options:
        logger.warning("Attempted to find best match in an empty list of options.")
        return None

    logger.debug(f"Finding best match for text: '{text}' in options: {options}")
    try:
        # Calculate distances: pair of (option, distance)
        distances = [(option, levenshtein_distance(text.lower(), option.lower())) for option in options]
        # Find the option with the minimum distance
        best_option, min_dist = min(distances, key=lambda item: item[1])
        logger.debug(f"Best match found: '{best_option}' with distance {min_dist}")
        return best_option
    except Exception as e:
        # Catching generic Exception here as Levenshtein might raise unexpected errors
        logger.error(f"Error finding best match for '{text}': {e}", exc_info=True)
        # Decide on fallback behavior: re-raise, return None, or a default? Returning None for now.
        return None


def preprocess_template_string(template: str) -> str:
    """
    Preprocess a template string by dedenting it.

    Args:
        template (str): The template string to preprocess.

    Returns:
        str: The preprocessed (dedented) template string.
    """
    if not isinstance(template, str):
        # Handle potential non-string input gracefully
        logger.warning(f"preprocess_template_string received non-string input: {type(template)}. Returning as is.")
        return str(template) # Or raise TypeError depending on desired strictness

    logger.debug("Preprocessing template string.")
    processed = textwrap.dedent(template).strip() # Add strip() to remove leading/trailing whitespace
    # logger.debug("Template string preprocessed.") # Too verbose maybe
    return processed


def extract_number_from_string(text: str) -> Optional[int]:
    """
    Extract the first integer found in the given string.

    Args:
        text (str): The string from which to extract the number.

    Returns:
        Optional[int]: The extracted integer, or None if no integer is found.
    """
    if not isinstance(text, str):
        logger.warning(f"extract_number_from_string received non-string input: {type(text)}")
        return None

    logger.debug(f"Attempting to extract number from string: '{text[:100]}...'") # Log truncated string
    # Find all sequences of digits
    numbers_found = re.findall(r"\d+", text)

    if numbers_found:
        try:
            # Take the first sequence found
            extracted_number = int(numbers_found[0])
            logger.debug(f"Numbers found: {numbers_found}. Extracted first number: {extracted_number}")
            return extracted_number
        except (ValueError, IndexError) as e:
            # Should ideally not happen with regex \d+ but good practice
            logger.error(f"Error converting found number '{numbers_found[0]}' to int: {e}", exc_info=True)
            return None
    else:
        logger.warning(f"No numeric digits found in the string: '{text[:100]}...'")
        return None


def parse_prompts_for_logging(prompts: Union[List[BaseMessage], StringPromptValue, ChatPromptValue, Dict, str]) -> Dict[str, str]:
    """
    Parses various prompt formats into a simple dictionary for logging.

    Args:
        prompts: The input prompts in various possible formats.

    Returns:
        A dictionary where keys are 'prompt_N' and values are string representations of the prompts.
    """
    logger.debug(f"Parsing prompts of type {type(prompts)} for logging.")
    parsed_prompts = {}
    try:
        if isinstance(prompts, StringPromptValue):
            parsed_prompts["prompt_1"] = prompts.text
        elif isinstance(prompts, ChatPromptValue):
            # Extract content from each message
            messages = prompts.messages if hasattr(prompts, 'messages') else []
            for i, msg in enumerate(messages):
                 parsed_prompts[f"prompt_{i+1}"] = str(getattr(msg, 'content', str(msg))) # Ensure content is str
        elif isinstance(prompts, list):
             # Assume list of BaseMessage or dicts
            for i, prompt in enumerate(prompts):
                content = getattr(prompt, 'content', None)
                if content is None and isinstance(prompt, dict):
                     content = prompt.get('content')
                parsed_prompts[f"prompt_{i+1}"] = str(content) if content is not None else str(prompt)
        elif isinstance(prompts, dict):
            # Handle dict, potentially with 'messages' key or other structure
            messages = prompts.get('messages', [])
            if messages:
                 for i, prompt in enumerate(messages):
                     content = getattr(prompt, 'content', None)
                     if content is None and isinstance(prompt, dict):
                         content = prompt.get('content')
                     parsed_prompts[f"prompt_{i+1}"] = str(content) if content is not None else str(prompt)
            else:
                # Fallback for generic dict
                parsed_prompts["prompt_1"] = str(prompts)
        elif isinstance(prompts, str):
             parsed_prompts["prompt_1"] = prompts
        else:
            # Fallback for any other type
            logger.warning(f"Unknown prompt type encountered: {type(prompts)}. Converting to string.")
            parsed_prompts["prompt_1"] = str(prompts)

        logger.debug(f"Parsed prompts for logging: {parsed_prompts}")
        return parsed_prompts
    except Exception as e:
        logger.error(f"Error parsing prompts for logging: {e}", exc_info=True)
        # Return a basic representation in case of error
        return {"error": f"Failed to parse prompts: {str(e)}", "original_prompts": str(prompts)}

def format_datetime(dt_obj: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Safely formats a datetime object to a string."""
    try:
        return dt_obj.strftime(fmt)
    except (AttributeError, ValueError, TypeError) as e:
        logger.warning(f"Could not format datetime object {dt_obj}: {e}")
        return str(dt_obj) # Fallback to string representation