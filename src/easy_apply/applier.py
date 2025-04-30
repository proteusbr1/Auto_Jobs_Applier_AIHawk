"""
Main module for the AIHawk Easy Apply functionality.
"""
import time
from typing import List, Optional, Tuple, Any
from loguru import logger
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from src.job import Job, JobCache
from src.llm.llm_manager import LLMAnswerer
import src.utils as utils
from app_config import (
    MIN_SCORE_APPLY,
    SALARY_EXPECTATIONS,
    USE_JOB_SCORE,
    USE_SALARY_EXPECTATIONS,
    TRYING_DEGUB,
)
from src.easy_apply.answer_storage import AnswerStorage
from src.easy_apply.job_info_extractor import JobInfoExtractor
from src.easy_apply.form_handler import FormHandler
from src.easy_apply.form_processors.processor_manager import FormProcessorManager
from src.easy_apply.file_uploader import FileUploader

class AIHawkEasyApplier:
    """
    Automates the process of applying to jobs on LinkedIn using the 'Easy Apply' feature.
    """

    def __init__(
        self,
        driver: WebDriver,
        resume_manager,
        set_old_answers: List[Tuple[str, str, str]],
        gpt_answerer: LLMAnswerer,
        resume_generator_manager=None,
        wait_time: int = 10,
        cache: JobCache = None,
    ):
        """
        Initialize the AIHawkEasyApplier with necessary components.
        
        Args:
            driver (WebDriver): The Selenium WebDriver instance.
            resume_manager: The resume manager instance.
            set_old_answers (List[Tuple[str, str, str]]): List of pre-defined answers.
            gpt_answerer (LLMAnswerer): The GPT answerer instance.
            resume_generator_manager: The resume generator manager instance.
                                    Can be None if using direct HTML resume.
            wait_time (int): The maximum time to wait for elements to appear.
            cache (JobCache): The job cache instance.
        """
        logger.debug("Initializing AIHawkEasyApplier")
        self.driver = driver
        self.wait = WebDriverWait(self.driver, wait_time)
        self.resume_manager = resume_manager
        self.resume_path = self.resume_manager.get_resume()
        self.set_old_answers = set_old_answers
        self.gpt_answerer = gpt_answerer
        self.resume_generator_manager = resume_generator_manager
        self.cache = cache
        
        # Initialize components
        self.answer_storage = AnswerStorage()
        self.job_info_extractor = JobInfoExtractor(driver, wait_time)
        self.form_handler = FormHandler(driver, wait_time)
        self.form_processor_manager = FormProcessorManager(driver, gpt_answerer, self.answer_storage, wait_time)
        self.file_uploader = FileUploader(driver, gpt_answerer, self.resume_path, wait_time)
        
        logger.debug("AIHawkEasyApplier initialized successfully")

    def main_job_apply(self, job: Job) -> bool:
        """ 
        Main method to apply for a job.
        
        Args:
            job (Job): The job object containing job details.
            
        Returns:
            bool: True if the application is successful, False otherwise.
        """
        logger.debug(f"Opening job: {job.link}")
        
        if job is None:
            logger.error("Job object is None. Cannot apply.")
            return False
        
        # Set up the job in the LLMAnswerer before any evaluation or form filling
        self.gpt_answerer.set_job(
            title=job.title,
            company=job.company,
            location=job.location,
            link=job.link,
            apply_method=job.apply_method,
            salary=job.salary,
            description=job.description,
            recruiter_link=job.recruiter_link,
            gpt_salary=job.gpt_salary,
            search_country=job.search_country,
        )
        logger.debug("Job successfully set up in LLMAnswerer.")
        
        try:
            self.driver.get(job.link)
            self.job_info_extractor.check_for_premium_redirect(job.link)
            job.description = self.job_info_extractor.get_job_description()
            job.salary = self.job_info_extractor.get_job_salary()
            # job.recruiter_link = self.job_info_extractor.get_job_recruiter()
            
            # Evaluate job score for logging purposes regardless of mode
            if job.score is None:
                job.score = self.gpt_answerer.evaluate_job(job)
                logger.debug(f"Job Score: {job.score}")
                self.cache.add_to_cache(job, "job_score")
                self.cache.write_to_file(job, "job_score")
            
            # If in debug mode, bypass score and salary checks
            if TRYING_DEGUB:
                logger.debug("Debug mode enabled. Bypassing score and salary checks.")
                
                # Still estimate salary for debugging purposes if enabled
                if USE_SALARY_EXPECTATIONS:
                    job.gpt_salary = self.gpt_answerer.estimate_salary(job)
                    logger.debug(f"Estimated salary: {job.gpt_salary} (ignored in debug mode)")
                
                logger.info("Debug mode: Proceeding with application regardless of score or salary.")
                # Continue with application process in debug mode
                proceed_with_application = True
            elif USE_JOB_SCORE:
                # Normal mode - check score against minimum
                proceed_with_application = False
                
                if job.score >= MIN_SCORE_APPLY:
                    logger.info(f"Job score is {job.score}. Proceeding with the application: {job.link}")
                    proceed_with_application = True
                    
                    # Check salary if enabled
                    if USE_SALARY_EXPECTATIONS:
                        job.gpt_salary = self.gpt_answerer.estimate_salary(job)
                        if SALARY_EXPECTATIONS > job.gpt_salary:
                            logger.info(f"Estimated salary {job.gpt_salary} is below expected {SALARY_EXPECTATIONS}. Skipping application.")
                            self.cache.add_to_cache(job, "skipped_low_salary")
                            self.cache.write_to_file(job, "skipped_low_salary")
                            proceed_with_application = False
                        else:
                            logger.info(f"Estimated salary {job.gpt_salary} is within expected {SALARY_EXPECTATIONS}.")
                    else:
                        logger.info(f"Salary is not being verified. Proceeding with the application.")
                else:
                    logger.info(f"Job score is {job.score}. Skipping application: {job.link}")
                    self.cache.add_to_cache(job, "skipped_low_score")
                    self.cache.write_to_file(job, "skipped_low_score")
                    proceed_with_application = False
            else:
                # Neither debug mode nor job score checking is enabled
                proceed_with_application = True
                logger.info("Neither debug mode nor job score checking is enabled. Proceeding with application.")
            
            # If we've determined not to proceed, return early
            if not proceed_with_application:
                return False
                
            # Continue with application process
            self.job_info_extractor.check_for_premium_redirect(job.link)
            # self.form_handler.scroll_page()
            
            # Attempt to click the 'Easy Apply' buttons sequentially
            success = self.form_handler.click_easy_apply_buttons_sequentially(job)
            
            if success:
                # If clicked successfully and the modal was displayed, continue with the filling
                self.form_handler.handle_job_search_safety_reminder()
                success = self._fill_application_form(job)
                if success:
                    logger.debug(f"Application process completed successfully for job: {job.title} at company {job.company}")
                    return True
                else:
                    logger.warning(f"Application process failed for job: {job.title} at company {job.company}")
                    # self.cache.write_to_file(job, "failed")
                    return False
            else:
                logger.warning(f"Clicked 'Easy Apply' buttons failed for job: {job.title} at company {job.company}")
                # self.cache.write_to_file(job, "failed")
                return False
        
        except Exception as e:
            logger.error(f"Failed to apply for the job: {e}", exc_info=True)
            utils.capture_screenshot(self.driver, "job_apply_exception")
            # self.cache.write_to_file(job, "failed")
            return False

    def _fill_application_form(self, job: Job, max_attempts: int = 10) -> bool:
        """
        Fills out the application form step by step.

        Args:
            job (Job): The job object.
            max_attempts (int): The maximum number of attempts to fill the form.
            
        Returns:
            bool: True if form submission is successful, False otherwise.
        """
        logger.debug(f"Filling out application form for job: {job.title} at {job.company}")
        try:
            attempts = 0
            error_count = 0
            max_errors = 1  # Maximum number of errors before skipping the job
            
            while attempts < max_attempts:
                try:
                    self._fill_up(job)
                    if self.form_handler.next_or_submit():
                        logger.debug("Application form submitted successfully")
                        return True

                    attempts += 1
                    logger.debug(f"Page {attempts} complete. Next page.")
                except KeyError as e:
                    logger.error(f"KeyError occurred during form filling: {e}. Skipping this job.")
                    utils.capture_screenshot(self.driver, "form_filling_key_error")
                    return False  # Skip to the next job immediately
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error during form filling (error {error_count}/{max_errors}): {e}")
                    utils.capture_screenshot(self.driver, f"form_filling_error_{error_count}")
                    
                    # If we've hit the maximum number of errors, skip this job
                    if error_count >= max_errors:
                        logger.error(f"Maximum errors ({max_errors}) reached. Skipping this job.")
                        # Log the current URL for debugging
                        current_url = self.driver.current_url
                        logger.error(f"Current job URL when skipping: {current_url}")
                        return False
                    
                    # Otherwise, try to continue with the next page
                    continue
                    
            logger.warning("Maximum attempts reached. Aborting application process.")
            utils.capture_screenshot(self.driver, "form_filling_max_attempts")
            return False
        except Exception as e:
            logger.error(f"An error occurred while filling the application form: {e}", exc_info=True)
            utils.capture_screenshot(self.driver, "form_filling_exception")
            # Log the current URL for debugging
            try:
                current_url = self.driver.current_url
                logger.error(f"Current job URL when exception occurred: {current_url}")
            except:
                pass
            return False

    def _fill_up(self, job: Job) -> None:
        """
        Fills up each section of the application form.

        Args:
            job (Job): The job object.
        """
        logger.debug(f"Starting to fill up form sections for job: {job.link}")

        try:
            # Find the modal content section (new structure)
            try:
                modal = self.wait.until(
                    lambda d: d.find_element(By.CLASS_NAME, "artdeco-modal")
                )
                logger.debug("Modal found successfully.")
                
                # Try to find the form within the modal
                form = modal.find_element(By.TAG_NAME, 'form')
                logger.debug("Form found within modal.")
            except (TimeoutException, NoSuchElementException):
                # Fall back to old structure if modal not found
                try:
                    easy_apply_content = self.wait.until(
                        lambda d: d.find_element(By.CLASS_NAME, "jobs-easy-apply-content")
                    )
                    logger.debug("Easy apply content section found successfully.")
                    form = easy_apply_content.find_element(By.TAG_NAME, 'form')
                    logger.debug("Form found within Easy Apply content.")
                except (TimeoutException, NoSuchElementException):
                    logger.info(
                        "Neither modal nor easy apply content found. Attempting to submit the application directly."
                    )
                    return

            # Find all form sections within the form
            # Try the new HTML structure first
            form_sections = form.find_elements(By.XPATH, ".//div[contains(@class, 'PhUvDQfCdKEziUOXPXmpuBzOwdFzCzynpE')]")
            
            # If no sections found with new class, try the old structure
            if not form_sections:
                form_sections = form.find_elements(By.XPATH, ".//div[contains(@class, 'jobs-easy-apply-form-section__grouping')]")
                
            # If still no sections found, try to find any form elements directly
            if not form_sections:
                form_sections = form.find_elements(By.XPATH, ".//div[contains(@class, 'fb-dash-form-element')]")
                
            logger.debug(f"Found {len(form_sections)} form sections to process.")

            # If no form sections found, try to find form elements directly
            if not form_sections:
                logger.debug("No form sections found. Looking for form elements directly.")
                
                # Try to find select containers (dropdowns)
                select_containers = form.find_elements(By.CSS_SELECTOR, "[data-test-text-entity-list-form-component]")
                if select_containers:
                    logger.debug(f"Found {len(select_containers)} select containers.")
                    form_sections.extend(select_containers)
                
                # Try to find text input containers
                text_input_containers = form.find_elements(By.CSS_SELECTOR, "[data-test-single-line-text-form-component]")
                if text_input_containers:
                    logger.debug(f"Found {len(text_input_containers)} text input containers.")
                    form_sections.extend(text_input_containers)
                
                # Try to find textarea containers
                textarea_containers = form.find_elements(By.CSS_SELECTOR, "[data-test-multiline-text-form-component]")
                if textarea_containers:
                    logger.debug(f"Found {len(textarea_containers)} textarea containers.")
                    form_sections.extend(textarea_containers)
                
                logger.debug(f"Found a total of {len(form_sections)} form elements to process.")
            
            # Process each form section
            for index, section in enumerate(form_sections):
                logger.debug(f"Processing form section {index + 1}/{len(form_sections)}")
                self._process_form_element(section, job)
            logger.debug("All form sections processed successfully.")

        except TimeoutException:
            logger.error(
                "Form section not found within the timeout period", exc_info=True
            )
            utils.capture_screenshot(self.driver, "form_timeout_error")
            raise
        except Exception as e:
            logger.error(
                f"An error occurred while filling up the form: {e}", exc_info=True
            )
            utils.capture_screenshot(self.driver, "form_fill_error")
            raise

    def _process_form_element(self, element: Any, job: Job) -> None:
        """
        Processes individual form elements.

        Args:
            element (Any): The form element to process.
            job (Job): The job object.
        """
        logger.debug("Processing form element")
        if self.form_processor_manager.is_upload_field(element):
            self.file_uploader.handle_upload_fields(element, job)
        else:
            self.form_processor_manager.process_form_section(element, job)
