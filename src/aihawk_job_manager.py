"""
AIHawk Job Manager module for automating LinkedIn job applications.
This is a wrapper module that imports the refactored functionality from the job_manager package.
"""
from loguru import logger

# Import the main AIHawkJobManager class from the refactored package
from src.job_manager import AIHawkJobManager, EnvironmentKeys

# For backward compatibility
from src.job import Job, JobCache

__all__ = ['AIHawkJobManager', 'EnvironmentKeys', 'Job', 'JobCache']
