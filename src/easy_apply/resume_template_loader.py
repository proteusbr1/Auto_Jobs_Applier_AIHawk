# src/easy_apply/resume_template_loader.py
"""
Utility function for loading the HTML resume template file.
"""
from pathlib import Path
from typing import Optional
from loguru import logger

# Define the default path relative to the project structure
DEFAULT_RESUME_TEMPLATE_PATH = Path("resumes/resume.html")

def load_resume_template(template_path: Path = DEFAULT_RESUME_TEMPLATE_PATH) -> Optional[str]:
    """
    Loads the resume HTML template content from the specified file path.

    Args:
        template_path (Path): The path to the HTML template file.
                               Defaults to DEFAULT_RESUME_TEMPLATE_PATH.

    Returns:
        Optional[str]: The HTML content as a string if successful, otherwise None.
    """
    if not isinstance(template_path, Path):
         template_path = Path(template_path) # Ensure Path object

    try:
        # Resolve to absolute path and check existence strictly
        resolved_path = template_path.resolve(strict=True)
        logger.info(f"Attempting to load resume template from: {resolved_path}")

        # Check if it's actually a file (resolve(strict=True) already checks existence)
        if not resolved_path.is_file():
            logger.error(f"Path exists but is not a file: {resolved_path}")
            return None

        # Read the file content
        content = resolved_path.read_text(encoding='utf-8')
        logger.debug(f"Resume template loaded successfully (length: {len(content)}).")
        return content

    except FileNotFoundError:
        logger.error(f"Resume template file not found at specified path: {template_path} (Resolved: {template_path.resolve() if not template_path.is_absolute() else template_path})")
        return None
    except PermissionError:
        logger.error(f"Permission denied reading resume template file: {template_path.resolve()}")
        return None
    except IOError as e:
        logger.error(f"IOError reading resume template file {template_path.resolve()}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred loading resume template {template_path.resolve()}: {e}", exc_info=True)
        return None