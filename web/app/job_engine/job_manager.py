"""
Job manager module for the Auto_Jobs_Applier_AIHawk web application.
This module handles job search and application for multiple users.
"""
from pathlib import Path
import time
import json
import os
from typing import Dict, List, Optional, Any, Tuple

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import WebDriverException
from flask import current_app
from loguru import logger

from app import db
from app.models import User, JobConfig, Resume, JobApplication
from app.job_engine.authenticator import LinkedInAuthenticator
from app.job_engine.session_manager import SessionManager
from app.job_engine.error_handler import ErrorHandler, JobError, ErrorSeverity, ErrorCategory


class JobManager:
    """
    Manages job search and application for a specific user.
    """
    
    def __init__(self, user_id: int, session_manager: SessionManager = None):
        """
        Initialize the job manager.
        
        Args:
            user_id (int): The ID of the user.
            session_manager (SessionManager, optional): The session manager to use.
        """
        self.user_id = user_id
        self.session_manager = session_manager
        self.driver = None
        self.authenticator = None
        self.user = User.query.get(user_id)
        
        if not self.user:
            logger.error(f"User with ID {user_id} not found")
            raise ValueError(f"User with ID {user_id} not found")
        
        logger.debug(f"JobManager initialized for user {user_id}")
    
    def start(self, job_config_id: Optional[int] = None, resume_id: Optional[int] = None) -> bool:
        """
        Start the job application process.
        
        Args:
            job_config_id (int, optional): The ID of the job configuration to use.
            resume_id (int, optional): The ID of the resume to use.
            
        Returns:
            bool: True if the process was started successfully, False otherwise.
        """
        try:
            # Get browser session
            if self.session_manager:
                self.driver = self.session_manager.get_session(self.user_id)
                if not self.driver:
                    logger.error(f"Failed to get browser session for user {self.user_id}")
                    return False
            else:
                logger.error(f"No session manager available for user {self.user_id}")
                return False
            
            # Initialize authenticator
            self.authenticator = LinkedInAuthenticator(self.driver, self.user_id, self.session_manager)
            
            # Log in to LinkedIn
            self.authenticator.start()
            
            # Get job configuration
            job_config = self._get_job_config(job_config_id)
            if not job_config:
                logger.error(f"No job configuration found for user {self.user_id}")
                return False
            
            # Get resume
            resume = self._get_resume(resume_id)
            if not resume:
                logger.error(f"No resume found for user {self.user_id}")
                return False
            
            # Start job search and application
            self._apply_to_jobs(job_config, resume)
            
            return True
        
        except Exception as e:
            logger.exception(f"Error starting job application process for user {self.user_id}: {e}")
            return False
        
        finally:
            # Release browser session
            if self.session_manager and self.driver:
                self.session_manager.release_session(self.user_id)
    
    def _get_job_config(self, job_config_id: Optional[int] = None) -> Optional[JobConfig]:
        """
        Get the job configuration to use.
        
        Args:
            job_config_id (int, optional): The ID of the job configuration to use.
            
        Returns:
            Optional[JobConfig]: The job configuration, or None if not found.
        """
        try:
            if job_config_id:
                # Get specific job configuration
                job_config = JobConfig.query.filter_by(id=job_config_id, user_id=self.user_id).first()
                if job_config:
                    return job_config
                logger.warning(f"Job configuration {job_config_id} not found for user {self.user_id}")
            
            # Get default job configuration
            job_config = JobConfig.query.filter_by(user_id=self.user_id, is_default=True).first()
            if job_config:
                return job_config
            
            # Get any job configuration
            job_config = JobConfig.query.filter_by(user_id=self.user_id).first()
            if job_config:
                return job_config
            
            logger.warning(f"No job configuration found for user {self.user_id}")
            return None
        
        except Exception as e:
            logger.exception(f"Error getting job configuration for user {self.user_id}: {e}")
            return None
    
    def _get_resume(self, resume_id: Optional[int] = None) -> Optional[Resume]:
        """
        Get the resume to use.
        
        Args:
            resume_id (int, optional): The ID of the resume to use.
            
        Returns:
            Optional[Resume]: The resume, or None if not found.
        """
        try:
            if resume_id:
                # Get specific resume
                resume = Resume.query.filter_by(id=resume_id, user_id=self.user_id).first()
                if resume:
                    return resume
                logger.warning(f"Resume {resume_id} not found for user {self.user_id}")
            
            # Get default resume
            resume = Resume.query.filter_by(user_id=self.user_id, is_default=True).first()
            if resume:
                return resume
            
            # Get any resume
            resume = Resume.query.filter_by(user_id=self.user_id).first()
            if resume:
                return resume
            
            logger.warning(f"No resume found for user {self.user_id}")
            return None
        
        except Exception as e:
            logger.exception(f"Error getting resume for user {self.user_id}: {e}")
            return None
    
    def _apply_to_jobs(self, job_config: JobConfig, resume: Resume):
        """
        Apply to jobs based on the job configuration.
        
        Args:
            job_config (JobConfig): The job configuration to use.
            resume (Resume): The resume to use.
        """
        logger.debug(f"Starting job application process for user {self.user_id} with job config {job_config.id}")
        
        # Initialize error handler
        error_handler = ErrorHandler(max_retries=3)
        
        try:
            # This is a placeholder for the actual job application logic
            # In a real implementation, this would:
            # 1. Search for jobs based on the job configuration
            # 2. Filter jobs based on blacklists and other criteria
            # 3. Apply to jobs using the resume
            # 4. Track application status
            
            # For now, we'll just log that we're applying to jobs
            logger.info(f"Applying to jobs for user {self.user_id} with job config {job_config.id} and resume {resume.id}")
            
            # Example of how to create a job application record
            application = self._create_job_application(
                job_config=job_config,
                resume=resume,
                job_id="123456789",
                job_title="Software Engineer",
                company_name="Example Company",
                location="San Francisco, CA",
                job_url="https://www.linkedin.com/jobs/view/123456789",
                job_description="Example job description",
                search_term="Software Engineer",
                search_location="San Francisco, CA"
            )
            
            # Example of error handling with retry logic
            retry_count = 0
            while retry_count <= error_handler.max_retries:
                try:
                    # Simulate a job application action that might fail
                    if retry_count == 0:
                        # Simulate an error on the first try
                        raise WebDriverException("Simulated error for demonstration")
                    
                    # If we get here, the operation succeeded
                    logger.info(f"Successfully applied to job after {retry_count} retries")
                    break
                
                except Exception as e:
                    # Handle the exception
                    context = {
                        'job_id': "123456789",
                        'retry_count': retry_count
                    }
                    
                    # Take a screenshot function
                    def take_screenshot():
                        try:
                            screenshot_dir = Path(current_app.config['USER_DATA_DIR'], str(self.user_id), 'screenshots')
                            os.makedirs(screenshot_dir, exist_ok=True)
                            screenshot_path = Path(screenshot_dir, f"error_{int(time.time())}.png")
                            self.driver.save_screenshot(str(screenshot_path))
                            return str(screenshot_path)
                        except Exception as screenshot_error:
                            logger.warning(f"Failed to take screenshot: {screenshot_error}")
                            return None
                    
                    # Handle the exception
                    error = error_handler.handle_exception(e, context, take_screenshot)
                    
                    # Update application status if we have an application
                    if application:
                        error_handler.update_application_status(application, error)
                    
                    # Check if we should retry
                    if error_handler.should_retry(error, retry_count):
                        retry_count += 1
                        delay = error_handler.get_retry_delay(retry_count)
                        logger.info(f"Retrying after {delay:.2f} seconds (attempt {retry_count}/{error_handler.max_retries})")
                        time.sleep(delay)
                    else:
                        logger.error(f"Not retrying after error: {error}")
                        break
        
        except Exception as e:
            # Handle any unexpected errors
            logger.exception(f"Unexpected error in job application process: {e}")
            
            # Create an error with high severity
            error = JobError(
                exception=e,
                severity=ErrorSeverity.HIGH,
                category=ErrorCategory.APPLICATION,
                message=f"Unexpected error in job application process: {str(e)}",
                context={'job_config_id': job_config.id, 'resume_id': resume.id}
            )
            
            # Log the error summary
            logger.error(f"Error summary: {error_handler.get_error_summary()}")
    
    def _create_job_application(
        self,
        job_config: JobConfig,
        resume: Resume,
        job_id: str,
        job_title: str,
        company_name: str,
        location: str,
        job_url: str,
        job_description: str,
        search_term: str,
        search_location: str,
        salary_range: Optional[str] = None,
        applicant_count: Optional[int] = None
    ) -> Optional[JobApplication]:
        """
        Create a job application record.
        
        Args:
            job_config (JobConfig): The job configuration used.
            resume (Resume): The resume used.
            job_id (str): The LinkedIn job ID.
            job_title (str): The job title.
            company_name (str): The company name.
            location (str): The job location.
            job_url (str): The job URL.
            job_description (str): The job description.
            search_term (str): The search term used to find the job.
            search_location (str): The search location used to find the job.
            salary_range (str, optional): The salary range.
            applicant_count (int, optional): The number of applicants.
            
        Returns:
            Optional[JobApplication]: The created job application, or None if creation failed.
        """
        try:
            # Check if we've already applied to this job
            existing_application = JobApplication.query.filter_by(
                user_id=self.user_id,
                job_id=job_id
            ).first()
            
            if existing_application:
                logger.debug(f"Already applied to job {job_id} for user {self.user_id}")
                return existing_application
            
            # Create new job application
            application = JobApplication(
                user_id=self.user_id,
                job_config_id=job_config.id,
                resume_id=resume.id,
                job_id=job_id,
                job_title=job_title,
                company_name=company_name,
                location=location,
                job_url=job_url,
                job_description=job_description,
                salary_range=salary_range,
                applicant_count=applicant_count,
                search_term=search_term,
                search_location=search_location,
                status="applied"
            )
            
            db.session.add(application)
            db.session.commit()
            
            logger.debug(f"Created job application {application.id} for user {self.user_id}")
            return application
        
        except Exception as e:
            logger.exception(f"Error creating job application for user {self.user_id}: {e}")
            db.session.rollback()
            return None
