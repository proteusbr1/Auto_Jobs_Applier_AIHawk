"""
Celery tasks for the Auto_Jobs_Applier_AIHawk web application.
This module contains asynchronous tasks for job application processing.
"""
from typing import Optional, Dict, Any, List
import time
import traceback

from flask import current_app
from celery import shared_task
from loguru import logger

from app import db, create_app
from app.models import User, JobConfig, Resume, JobApplication
from app.job_engine.session_manager import SessionManager
from app.job_engine.job_manager import JobManager


# Global session manager instance
_session_manager = None


def get_session_manager() -> SessionManager:
    """
    Get or create the global session manager instance.
    
    Returns:
        SessionManager: The session manager instance.
    """
    global _session_manager
    if _session_manager is None:
        max_sessions = current_app.config.get('MAX_BROWSER_SESSIONS', 10)
        session_timeout = current_app.config.get('BROWSER_SESSION_TIMEOUT', 3600)
        _session_manager = SessionManager(max_sessions=max_sessions, session_timeout=session_timeout)
        logger.debug(f"Created global session manager with max_sessions={max_sessions}, session_timeout={session_timeout}")
    return _session_manager


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def apply_to_jobs(self, user_id: int, job_config_id: Optional[int] = None, resume_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Apply to jobs for a user.
    
    Args:
        self: The Celery task instance.
        user_id (int): The ID of the user.
        job_config_id (int, optional): The ID of the job configuration to use.
        resume_id (int, optional): The ID of the resume to use.
        
    Returns:
        Dict[str, Any]: A dictionary with the task result.
    """
    logger.info(f"Starting job application task for user {user_id}")
    
    # Create Flask application context
    app = create_app()
    with app.app_context():
        try:
            # Get session manager
            session_manager = get_session_manager()
            
            # Create job manager
            job_manager = JobManager(user_id, session_manager)
            
            # Start job application process
            success = job_manager.start(job_config_id, resume_id)
            
            if success:
                logger.info(f"Job application task completed successfully for user {user_id}")
                return {
                    'status': 'success',
                    'message': 'Job application process completed successfully',
                    'user_id': user_id
                }
            else:
                logger.error(f"Job application task failed for user {user_id}")
                return {
                    'status': 'error',
                    'message': 'Job application process failed',
                    'user_id': user_id
                }
        
        except Exception as e:
            logger.exception(f"Error in job application task for user {user_id}: {e}")
            
            # Retry the task if it's not the last retry
            if self.request.retries < self.max_retries:
                logger.info(f"Retrying job application task for user {user_id} ({self.request.retries + 1}/{self.max_retries})")
                self.retry(exc=e)
            
            return {
                'status': 'error',
                'message': f'Error in job application task: {str(e)}',
                'user_id': user_id,
                'traceback': traceback.format_exc()
            }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def search_jobs(self, user_id: int, job_config_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Search for jobs for a user.
    
    Args:
        self: The Celery task instance.
        user_id (int): The ID of the user.
        job_config_id (int, optional): The ID of the job configuration to use.
        
    Returns:
        Dict[str, Any]: A dictionary with the task result.
    """
    logger.info(f"Starting job search task for user {user_id}")
    
    # Create Flask application context
    app = create_app()
    with app.app_context():
        try:
            # This is a placeholder for the actual job search logic
            # In a real implementation, this would:
            # 1. Get the job configuration
            # 2. Search for jobs based on the configuration
            # 3. Save the job listings to the database
            
            # For now, we'll just log that we're searching for jobs
            logger.info(f"Searching for jobs for user {user_id} with job config {job_config_id}")
            
            # Simulate some work
            time.sleep(2)
            
            return {
                'status': 'success',
                'message': 'Job search completed successfully',
                'user_id': user_id,
                'job_config_id': job_config_id,
                'jobs_found': 10  # Placeholder
            }
        
        except Exception as e:
            logger.exception(f"Error in job search task for user {user_id}: {e}")
            
            # Retry the task if it's not the last retry
            if self.request.retries < self.max_retries:
                logger.info(f"Retrying job search task for user {user_id} ({self.request.retries + 1}/{self.max_retries})")
                self.retry(exc=e)
            
            return {
                'status': 'error',
                'message': f'Error in job search task: {str(e)}',
                'user_id': user_id,
                'traceback': traceback.format_exc()
            }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def generate_resume(self, user_id: int, base_resume_id: int, job_title: str, company_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate a resume for a specific job.
    
    Args:
        self: The Celery task instance.
        user_id (int): The ID of the user.
        base_resume_id (int): The ID of the base resume to use.
        job_title (str): The job title to target.
        company_name (str, optional): The company name to target.
        
    Returns:
        Dict[str, Any]: A dictionary with the task result.
    """
    logger.info(f"Starting resume generation task for user {user_id}")
    
    # Create Flask application context
    app = create_app()
    with app.app_context():
        try:
            # This is a placeholder for the actual resume generation logic
            # In a real implementation, this would:
            # 1. Get the base resume
            # 2. Generate a targeted resume using AI
            # 3. Save the generated resume to the database
            
            # For now, we'll just log that we're generating a resume
            logger.info(f"Generating resume for user {user_id} with base resume {base_resume_id} for job {job_title} at {company_name or 'any company'}")
            
            # Simulate some work
            time.sleep(3)
            
            return {
                'status': 'success',
                'message': 'Resume generation completed successfully',
                'user_id': user_id,
                'base_resume_id': base_resume_id,
                'job_title': job_title,
                'company_name': company_name,
                'generated_resume_id': 123  # Placeholder
            }
        
        except Exception as e:
            logger.exception(f"Error in resume generation task for user {user_id}: {e}")
            
            # Retry the task if it's not the last retry
            if self.request.retries < self.max_retries:
                logger.info(f"Retrying resume generation task for user {user_id} ({self.request.retries + 1}/{self.max_retries})")
                self.retry(exc=e)
            
            return {
                'status': 'error',
                'message': f'Error in resume generation task: {str(e)}',
                'user_id': user_id,
                'traceback': traceback.format_exc()
            }


@shared_task
def cleanup_browser_sessions() -> Dict[str, Any]:
    """
    Clean up inactive browser sessions.
    
    Returns:
        Dict[str, Any]: A dictionary with the task result.
    """
    logger.info("Starting browser session cleanup task")
    
    # Create Flask application context
    app = create_app()
    with app.app_context():
        try:
            # Get session manager
            session_manager = get_session_manager()
            
            # The session manager already has a cleanup thread,
            # but we can trigger an immediate cleanup here
            
            # For now, we'll just log that we're cleaning up sessions
            logger.info("Cleaning up browser sessions")
            
            return {
                'status': 'success',
                'message': 'Browser session cleanup completed successfully'
            }
        
        except Exception as e:
            logger.exception(f"Error in browser session cleanup task: {e}")
            
            return {
                'status': 'error',
                'message': f'Error in browser session cleanup task: {str(e)}',
                'traceback': traceback.format_exc()
            }
