# src/job_manager/__init__.py
"""
Job Manager package for handling website automation tasks,
specifically focused on job searching and application workflows.

This package contains modules for navigating web pages, extracting information (e.g., job details),
filtering data, and performing application actions.
"""

# Export the main orchestrator class
from .job_manager import JobManager

# Optionally export other components if they are used directly elsewhere
from .job_filter import JobFilter
from .job_extractor import JobExtractor
from .job_navigator import JobNavigator
from .job_applier import JobApplier
from .environment_keys import EnvironmentKeys # Keep if used externally, otherwise maybe internal detail

__all__ = [
    'JobManager',
    'JobFilter',
    'JobExtractor',
    'JobNavigator',
    'JobApplier',
    'EnvironmentKeys' # Optional export
]