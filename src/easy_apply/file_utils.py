# src/easy_apply/file_utils.py
"""
Utility functions for file operations, particularly for generating
safe and descriptive filenames for generated documents like resumes and cover letters.
"""
import re
from typing import Optional
from pathlib import Path
from loguru import logger

# Constants for filename generation
MAX_TITLE_LENGTH = 40 # Reduced max length
MAX_COMPANY_LENGTH = 30 # Reduced max length
MAX_FILENAME_LENGTH = 150 # Reduced max overall length for broader compatibility
DEFAULT_PREFIX = "Document"
ELLIPSIS = "..."

def sanitize_filename_component(text: str) -> str:
    """
    Sanitizes a string component for use in a filename.
    Removes invalid characters and replaces whitespace with underscores.

    Args:
        text (str): The input string.

    Returns:
        str: A sanitized string suitable for filenames. Returns 'NA' if input is empty.
    """
    if not text or not isinstance(text, str):
        return "NA" # Not Applicable/Available
    # Remove characters not allowed in filenames (adjust regex as needed for OS)
    # Keeps alphanumeric, underscore, hyphen, period. Replaces others with underscore.
    sanitized = re.sub(r'[^\w\-.]', '_', text)
    # Replace multiple consecutive underscores/hyphens/periods with a single underscore
    sanitized = re.sub(r'[_.-]+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    # Replace spaces with underscores
    sanitized = sanitized.replace(' ', '_')
    # Return 'NA' if sanitization results in empty string
    return sanitized if sanitized else "NA"

def truncate_text(text: str, max_length: int) -> str:
    """
    Truncates text to a maximum length, adding ellipsis if needed.

    Args:
        text (str): The input string.
        max_length (int): The maximum desired length (including ellipsis).

    Returns:
        str: The potentially truncated string.
    """
    if max_length <= len(ELLIPSIS): # Need space for ellipsis
         return text[:max_length] # Just truncate hard if max_length is too small

    if len(text) > max_length:
        return text[:max_length - len(ELLIPSIS)] + ELLIPSIS
    else:
        return text

def generate_humanized_filename(
    prefix: Optional[str] = None,
    job_title: Optional[str] = None,
    company_name: Optional[str] = None,
    datetime_str: Optional[str] = None,
    extension: str = ".pdf"
) -> str:
    """
    Generates a sanitized, human-readable filename for generated documents.

    Constructs filename like: Prefix_JobTitle_CompanyName_DateTime.ext
    Applies sanitization and truncation rules.

    Args:
        prefix (Optional[str]): Filename prefix (e.g., "Resume"). Defaults to "Document".
        job_title (Optional[str]): Job title component.
        company_name (Optional[str]): Company name component.
        datetime_str (Optional[str]): Datetime string component.
        extension (str): File extension including the dot (e.g., ".pdf").

    Returns:
        str: The generated filename.
    """
    prefix_clean = sanitize_filename_component(prefix or DEFAULT_PREFIX)
    title_clean = sanitize_filename_component(job_title or "Job")
    company_clean = sanitize_filename_component(company_name or "Company")
    datetime_clean = sanitize_filename_component(datetime_str or "") # Allow empty datetime

    # Truncate individual components before assembly
    title_trunc = truncate_text(title_clean, MAX_TITLE_LENGTH)
    company_trunc = truncate_text(company_clean, MAX_COMPANY_LENGTH)

    # Assemble base filename parts
    parts = [prefix_clean, title_trunc, company_trunc, datetime_clean]
    base_filename = "_".join(filter(None, parts)) # Join non-empty parts with underscore

    # Ensure overall length limit
    # Calculate max length for base filename allowing for extension
    max_base_len = MAX_FILENAME_LENGTH - len(extension)
    final_base = truncate_text(base_filename, max_base_len)

    final_filename = f"{final_base}{extension}"
    logger.trace(f"Generated filename: {final_filename}")
    return final_filename


def check_file_size(file_path: Path, max_size_bytes: int) -> None:
    """
    Checks if the file size exceeds a maximum limit.

    Args:
        file_path (Path): Path object for the file.
        max_size_bytes (int): Maximum allowed size in bytes.

    Raises:
        ValueError: If the file size exceeds the limit or file doesn't exist.
        IOError: If the file size cannot be read.
    """
    if not isinstance(file_path, Path):
         file_path = Path(file_path) # Convert if string

    try:
        if not file_path.is_file():
             logger.error(f"File not found for size check: {file_path}")
             raise ValueError(f"File not found: {file_path}")

        file_size = file_path.stat().st_size
        logger.debug(f"Checking file size for {file_path}: {file_size} bytes (Limit: {max_size_bytes} bytes)")

        if file_size > max_size_bytes:
            logger.error(f"File size ({file_size} bytes) exceeds maximum limit ({max_size_bytes} bytes) for {file_path}")
            raise ValueError(f"File size exceeds limit ({max_size_bytes} bytes): {file_path}")

        logger.trace(f"File size check passed for {file_path}")

    except OSError as e:
         logger.error(f"OS error checking file size for {file_path}: {e}", exc_info=True)
         raise IOError(f"Could not check file size for {file_path}: {e}") from e
    except ValueError: # Re-raise ValueError from file not found check
         raise
    except Exception as e:
         logger.error(f"Unexpected error checking file size for {file_path}: {e}", exc_info=True)
         raise IOError(f"Unexpected error checking file size for {file_path}: {e}") from e