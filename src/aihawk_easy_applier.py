"""
AIHawk Easy Applier module for automating LinkedIn job applications.
This is a wrapper module that imports the refactored functionality from the easy_apply package.
"""
import sys
from loguru import logger

# Import the main AIHawkEasyApplier class from the refactored package
from src.easy_apply import AIHawkEasyApplier

# Import the resume template loader to maintain backward compatibility
from src.easy_apply.resume_template_loader import load_resume_template

# Load the resume template for backward compatibility
logger.debug("Loading resume template.")
USER_RESUME_HTML = load_resume_template()  
if USER_RESUME_HTML is None:
    logger.error("Failed to load the resume template. Exiting application.")
    sys.exit(1)
