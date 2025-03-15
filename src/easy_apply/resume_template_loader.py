"""
Module for loading resume templates from files.
"""
import os
from pathlib import Path
from typing import Optional
from loguru import logger
import sys

def load_resume_template() -> Optional[str]:
    """
    Loads the resume HTML template from the specified file path.

    Returns:
        Optional[str]: The content of the resume HTML template if loaded successfully; otherwise, None.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        PermissionError: If there is a permission issue accessing the file.
        IOError: If an I/O error occurs while reading the file.
        Exception: For any other unforeseen errors.
    """
    file_path = "resumes/resume.html"
    try:
        path = Path(file_path).resolve(strict=True)
        logger.debug(f"Attempting to load resume template from: {path}")

        if not path.is_file():
            logger.error(f"The path provided is not a file: {path}")
            raise FileNotFoundError(f"The path provided is not a file: {path}")

        if not os.access(path, os.R_OK):
            logger.error(f"Permission denied while trying to read the file: {path}")
            raise PermissionError(f"Permission denied while trying to read the file: {path}")

        with path.open('r', encoding='utf-8') as file:
            content = file.read()
            logger.debug("Resume template loaded successfully.")
            return content

    except FileNotFoundError as fnf_error:
        logger.exception(f"File not found error: {fnf_error}")
        raise

    except PermissionError as perm_error:
        logger.exception(f"Permission error: {perm_error}")
        raise

    except IOError as io_error:
        logger.exception(f"I/O error occurred while reading the resume template: {io_error}")
        raise

    except Exception as e:
        logger.exception(f"An unexpected error occurred while loading the resume template: {e}")
        raise
