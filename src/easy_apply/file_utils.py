"""
Utility functions for file operations in the Easy Apply process.
"""
import os
import re
from datetime import datetime
from loguru import logger

# Constants for filename limits
MAX_TITLE_LENGTH = 50
MAX_COMPANY_LENGTH = 50
MAX_FILENAME_LENGTH = 255

def sanitize_filename(text: str) -> str:
    """
    Sanitizes the text by removing invalid characters and replacing spaces with underscores.
    
    Args:
        text (str): The input string to sanitize.
    
    Returns:
        str: A sanitized string safe for use in filenames.
    """
    sanitized = re.sub(r'[^\w\-_. ]', '_', text).replace(' ', '_')
    return sanitized

def truncate_text(text: str, max_length: int) -> str:
    """
    Truncates the text to the specified maximum length, adding '...' if necessary.
    
    Args:
        text (str): The input string to truncate.
        max_length (int): The maximum allowed length of the string.
    
    Returns:
        str: The truncated string with ellipses if truncation occurred.
    """
    return text if len(text) <= max_length else text[:max_length-3] + '...'

def generate_humanized_filename(prefix: str, job_title: str, company_name: str, datetime_str: str) -> str:
    """
    Generates a humanized filename by sanitizing and truncating its components.
    
    Args:
        prefix (str): The prefix for the filename (e.g., 'Resume', 'Cover_Letter').
        job_title (str): The job title to include in the filename.
        company_name (str): The company name to include in the filename.
        datetime_str (str): The datetime string to include in the filename.
    
    Returns:
        str: A sanitized and appropriately truncated filename.
    """
    # Sanitize inputs
    job_title_sanitized = sanitize_filename(job_title)
    company_name_sanitized = sanitize_filename(company_name)
    
    # Truncate if necessary
    job_title_truncated = truncate_text(job_title_sanitized, MAX_TITLE_LENGTH)
    company_name_truncated = truncate_text(company_name_sanitized, MAX_COMPANY_LENGTH)
    
    # Construct the filename
    filename = f"{prefix}_{job_title_truncated}_{company_name_truncated}_{datetime_str}.pdf"
    
    # Ensure the total filename length does not exceed the maximum
    if len(filename) > MAX_FILENAME_LENGTH:
        excess_length = len(filename) - MAX_FILENAME_LENGTH
        # Prioritize truncating the job title
        if len(job_title_truncated) > 10:
            new_title_length = max(len(job_title_truncated) - excess_length, 10)
            job_title_truncated = truncate_text(job_title_sanitized, new_title_length)
            filename = f"{prefix}_{job_title_truncated}_{company_name_truncated}_{datetime_str}.pdf"
            logger.debug(f"Truncated job title to fit filename length: {job_title_truncated}")
            excess_length = len(filename) - MAX_FILENAME_LENGTH
        
        # If still too long, truncate the company name
        if len(filename) > MAX_FILENAME_LENGTH and len(company_name_truncated) > 10:
            new_company_length = max(len(company_name_truncated) - excess_length, 10)
            company_name_truncated = truncate_text(company_name_sanitized, new_company_length)
            filename = f"{prefix}_{job_title_truncated}_{company_name_truncated}_{datetime_str}.pdf"
            logger.debug(f"Truncated company name to fit filename length: {company_name_truncated}")
            excess_length = len(filename) - MAX_FILENAME_LENGTH
        
        # If still exceeding, truncate the entire filename
        if len(filename) > MAX_FILENAME_LENGTH:
            filename = truncate_text(filename, MAX_FILENAME_LENGTH - 4) + ".pdf"
            logger.debug(f"Truncated entire filename to fit maximum length: {filename}")
    
    return filename

def check_file_size(file_path: str, max_size: int) -> None:
    """
    Checks if the file size exceeds the maximum allowed size.
    
    Args:
        file_path (str): The path to the file.
        max_size (int): The maximum allowed size in bytes.
    
    Raises:
        ValueError: If the file size exceeds the maximum allowed size.
    """
    file_size = os.path.getsize(file_path)
    logger.debug(f"Checking file size for {file_path}: {file_size} bytes")
    if file_size > max_size:
        logger.error(f"File size for {file_path} exceeds the maximum allowed size of {max_size} bytes.")
        raise ValueError(f"File size for {file_path} exceeds the maximum allowed size of {max_size} bytes.")
    logger.debug(f"File size for {file_path} is within the allowed limit.")
