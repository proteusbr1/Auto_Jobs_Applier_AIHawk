# aihawk_easy_applier.py
import base64
import json
import os
import re
import time
from typing import List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path
from weasyprint import HTML
from jinja2 import Template
import sys

from httpx import HTTPStatusError
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Frame, Paragraph
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementNotInteractableException,
)
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from app_config import (
    MIN_SCORE_APPLY,
    SALARY_EXPECTATIONS,
    USE_JOB_SCORE,
    USE_SALARY_EXPECTATIONS,
    TRYING_DEGUB,
)
from data_folder.personal_info import USER_RESUME_SUMMARY, USER_RESUME_CHATGPT
import src.utils as utils
from src.llm.llm_manager import GPTAnswerer
from loguru import logger
from src.job import Job, JobCache


if TRYING_DEGUB:
    SALARY_EXPECTATIONS = 0
    MIN_SCORE_APPLY = 0

# @staticmethod
def load_resume_template() -> Optional[str]:
    """
    Loads the resume HTML template from the specified file path.

    Args:
        file_path (str): The path to the HTML resume template file.

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

logger.debug("Loading resume template.")
USER_RESUME_HTML = load_resume_template()  
if USER_RESUME_HTML is None:
    logger.error("Failed to load the resume template. Exiting application.")
    sys.exit(1)

class AIHawkEasyApplier:
    """
    Automates the process of applying to jobs on LinkedIn using the 'Easy Apply' feature.
    """

    def __init__(
        self,
        driver: Any,
        resume_manager,
        set_old_answers: List[Tuple[str, str, str]],
        gpt_answerer: GPTAnswerer,
        resume_generator_manager,
        wait_time: int = 10,
        cache: JobCache = None,
    ):
        logger.debug("Initializing AIHawkEasyApplier")
        self.driver = driver
        self.wait = WebDriverWait(self.driver, wait_time)
        self.resume_manager = resume_manager
        self.resume_path = self.resume_manager.get_resume()
        self.set_old_answers = set_old_answers
        self.gpt_answerer = gpt_answerer
        self.resume_generator_manager = resume_generator_manager
        self.cache = cache
        self.all_questions = self._load_questions_from_json()

        logger.debug("AIHawkEasyApplier initialized successfully")

    def main_job_apply(self, job: Job) -> bool:
        """ 
        Main method to apply for a job.
        
        :param job: The job object containing job details.
        :return: True if the application is successful, False otherwise.
        """
        logger.debug(f"Opening job: {job.link}")
        
        if job is None:
            logger.error("Job object is None. Cannot apply.")
            return False
        
        # Set up the job in the GPTAnswerer before any evaluation or form filling
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
        )
        logger.debug("Job successfully set up in GPTAnswerer.")
        
        try:
            self.driver.get(job.link)
            self._check_for_premium_redirect(job)
            job.description = self._get_job_description()
            job.salary = self._get_job_salary()
            # job.recruiter_link = self._get_job_recruiter()
            
            if USE_JOB_SCORE:
                logger.debug("Evaluating job score using GPT.")
                if job.score is None:
                    job.score = self.gpt_answerer.evaluate_job(job)
                    logger.debug(f"Job Score: {job.score}")
                    self.cache.add_to_cache(job, "job_score")
                    self.cache.write_to_file(job, "job_score")
                
                if job.score >= MIN_SCORE_APPLY:
                    logger.info(f"Job score is {job.score}. Proceeding with the application.")
                    if USE_SALARY_EXPECTATIONS:
                        job.gpt_salary = self.gpt_answerer.estimate_salary(job)
                        if SALARY_EXPECTATIONS > job.gpt_salary:
                            logger.info(f"Estimated salary {job.gpt_salary} is below expected {SALARY_EXPECTATIONS}. Skipping application.")
                            self.cache.add_to_cache(job, "skipped_low_salary")
                            self.cache.write_to_file(job, "skipped_low_salary")
                            return False
                        else:
                            logger.info(f"Estimated salary {job.gpt_salary} is within expected {SALARY_EXPECTATIONS}. Proceeding with the application.")
                    else:
                        logger.info(f"Salary is not being verified. Proceeding with the application.")
                else:
                    logger.info(f"Job score is {job.score}. Skipping application: {job.link}")
                    self.cache.add_to_cache(job, "skipped_low_score")
                    self.cache.write_to_file(job, "skipped_low_score")
                    return False
            
            self._check_for_premium_redirect(job)
            # self._scroll_page()
            
            # Attempt to click the 'Easy Apply' buttons sequentially
            success = self._click_easy_apply_buttons_sequentially(job)
            
            if success:
                # If clicked successfully and the modal was displayed, continue with the filling
                self._handle_job_search_safety_reminder()
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
            # self.cache.write_to_file(job, "failed")
            return False

    def _check_for_premium_redirect(self, job: Any, max_attempts=3):
        """
        Check if the browser is redirected to the LinkedIn Premium page and attempt to navigate back.

        :param job: The job object containing the job link.
        :param max_attempts: Maximum number of attempts to return to the job page.
        """
        current_url = self.driver.current_url
        attempts = 0

        while "linkedin.com/premium" in current_url and attempts < max_attempts:
            logger.warning(
                "Redirected to LinkedIn Premium page. Attempting to return to job page."
            )
            attempts += 1

            self.driver.get(job.link)
            try:
                self.wait.until(EC.url_to_be(job.link))
                logger.debug(f"Returned to job page: {job.link}")
            except TimeoutException:
                logger.warning(
                    f"Attempt {attempts}: Timed out waiting to return to job page: {job.link}"
                )
            current_url = self.driver.current_url

        if "linkedin.com/premium" in current_url:
            logger.error(
                f"Failed to return to job page after {max_attempts} attempts. Cannot apply for the job."
            )
            raise Exception(
                f"Redirected to LinkedIn Premium page and failed to return after {max_attempts} attempts. Job application aborted."
            )

    def _get_job_description(self) -> str:
        """
        Retrieves the job description from the job page.

        :return: The job description text.
        """
        logger.debug("Getting job description")
        try:
            try:
                # Wait until the 'See more description' button is clickable
                see_more_button = self.wait.until(EC.element_to_be_clickable((By.XPATH,'//button[@aria-label="Click to see more description"]',)))
                actions = ActionChains(self.driver)
                actions.move_to_element(see_more_button).click().perform()
                logger.debug(
                    "Clicked 'See more description' button to expand job description"
                )
            except (NoSuchElementException, TimeoutException):
                logger.debug(
                    "'See more description' button not found, proceeding with available description"
                )

            # Wait until the job description element is present
            description_element = self.wait.until(
                EC.presence_of_element_located(
                    (By.CLASS_NAME, "jobs-description-content__text")
                )
            )
            description = description_element.text
            if description:
                logger.debug("Job description retrieved successfully")
            else:
                logger.warning("Job description element found but text is empty")
            return description
        except NoSuchElementException as e:
            logger.warning("Job description element not found.")
            raise Exception("Job description element not found") from e
        except TimeoutException as te:
            logger.warning("Timed out waiting for the job description element.")
            utils.capture_screenshot(self.driver, "job_description_timeout")
            raise Exception("Timed out waiting for the job description element") from te
        except Exception as e:
            logger.warning(
                f"Unexpected error in _get_job_description: {e}", exc_info=True
            )
            raise Exception("Error getting job description") from e

    def _get_job_salary(self) -> str:
        """
        Retrieves the job salary from the job page.

        :return: The job salary text.
        """
        logger.debug("Getting job salary")
        try:
            salary_element = self.driver.find_element(By.XPATH,"//li[contains(@class, 'job-insight--highlight')]//span[@dir='ltr']")
            salary = salary_element.text.strip()
            if salary:
                logger.debug(f"Job salary retrieved successfully: {salary}")
                return salary
            else:
                logger.warning("Salary element found but text is empty")
                return "Not specified"
        except NoSuchElementException:
            logger.debug("Salary element not found.")
            return ""
        except Exception as e:
            logger.warning(f"Unexpected error in _get_job_salary: {e}", exc_info=True)
            return ""

    def _get_job_recruiter(self):
        """
        Retrieves the job recruiter information from the job page.
        """
        logger.debug("Getting job recruiter information")
        try:
            hiring_team_section = self.wait.until(EC.presence_of_element_located((By.XPATH, '//h2[text()="Meet the hiring team"]')))
            logger.debug("Hiring team section found")

            recruiter_elements = hiring_team_section.find_elements(By.XPATH, './/following::a[contains(@href, "linkedin.com/in/")]')

            if recruiter_elements:
                recruiter_element = recruiter_elements[0]
                recruiter_link = recruiter_element.get_attribute("href")
                logger.debug(f"Job recruiter link retrieved successfully: {recruiter_link}")
                return recruiter_link
            else:
                logger.debug("No recruiter link found in the hiring team section")
                return ""
        except TimeoutException:
            logger.warning("Hiring team section not found within the timeout period")
            return ""
        except Exception as e:
            logger.warning(f"Failed to retrieve recruiter information: {e}", exc_info=True)
            return "" 

    def _handle_job_search_safety_reminder(self) -> None:
        """
        Handles the 'Job search safety reminder' modal if it appears.
        """
        try:
            modal = self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "artdeco-modal")))
            logger.debug("Job search safety reminder modal detected.")
            continue_button = modal.find_element(By.XPATH, '//button[contains(., "Continue applying")]')
            if continue_button:
                continue_button.click()
                logger.debug("Clicked 'Continue applying' button in modal.")
        except NoSuchElementException:
            logger.debug("Job search safety reminder elements not found.")
        except TimeoutException:
            logger.debug("No 'Job search safety reminder' modal detected.")
        except Exception as e:
            logger.warning(f"Unexpected error while handling safety reminder modal: {e}",exc_info=True,)
            
    def _scroll_page(self) -> None:
        """
        Scrolls the page up and down to ensure all elements are loaded.
        """
        logger.debug("Scrolling the page")
        try:
            scrollable_element = self.driver.find_element(By.TAG_NAME, "html")
            utils.scroll_slow(self.driver, scrollable_element, step=300, reverse=False)
            utils.scroll_slow(self.driver, scrollable_element, step=300, reverse=True)
            logger.debug("Page scrolled successfully")
        except Exception as e:
            logger.warning(f"Failed to scroll the page: {e}", exc_info=True)            

    def _click_easy_apply_buttons_sequentially(self, job: Job) -> bool:
        """
        Attempts to click each 'Easy Apply' button found sequentially.
        
        :param job: The job object containing job details.
        :return: True if the application is successful, False otherwise.
        """
        buttons = self._2_find_easy_apply_buttons(job)
        
        if not buttons:
            logger.error("No 'Easy Apply' button found.")
            # self.cache.write_to_file(job, "failed")
            return False
        
        for index, button in enumerate(buttons, start=1):
            try:
                logger.debug(f"Trying to click 'Easy Apply' button number {index}.")

                if not self._2_is_element_clickable(button):
                    logger.debug(f"'Easy Apply' button number {index} is not clickable.")
                    continue

                ActionChains(self.driver).move_to_element(button).click().perform()
                logger.debug(f"Successfully clicked 'Easy Apply' button number {index}.")
                
                # Check if the modal opened correctly
                if self._2_is_modal_displayed():
                    logger.debug("The 'Easy Apply' modal displayed successfully.")
                    return True
                else:
                    logger.debug("The 'Easy Apply' modal did not display after clicking.")
                    self.driver.refresh()
                    continue  # Try the next button
                    
            except (NoSuchElementException, ElementNotInteractableException, TimeoutException) as e:
                self.driver.refresh()
                continue  # Try the next button
        
        logger.error("All 'Easy Apply' buttons clicked failed.")
        # self.cache.write_to_file(job, "failed")
        return False

    def _2_find_easy_apply_buttons(self, job: Job) -> List[WebElement]:
        """
        Finds all 'Easy Apply' buttons corresponding to the specific job.
        
        :param job: The job object containing job details.
        :return: List of WebElements of the found 'Easy Apply' buttons.
        """
        logger.debug(f"Searching for 'Easy Apply' buttons for job ID: {job.link}")
        
        # More specific XPath using data-job-id
        # xpath = f'//button[@data-job-id="{job.link}" and contains(@aria-label, "Easy Apply")]'
        xpath = '//button[contains(@aria-label, "Easy Apply") and contains(@class, "jobs-apply-button")]'
        
        try:
            buttons = self.wait.until(lambda d: d.find_elements(By.XPATH, xpath))
            logger.debug(f"Number of 'Easy Apply' buttons found: {len(buttons)}")
            return buttons
        except TimeoutException:
            logger.warning(f"No 'Easy Apply' button found for job ID: {job.link}")
            return []

    def _2_is_element_clickable(self, element: WebElement) -> bool:
        """
        Checks if a given WebElement is clickable.

        :param element: The WebElement to check.
        :return: True if the element is clickable, False otherwise.
        """
        try:
            self.wait.until(EC.visibility_of(element))
            self.wait.until(EC.element_to_be_clickable(element))
            logger.debug("Element is visible and clickable.")
            return True
        except Exception as e:
            logger.debug(f"Element is not clickable: {e}")
            return False

    def _2_is_modal_displayed(self) -> bool:
        """
        Checks if the '.artdeco-modal' is displayed.
        
        :return: True if the modal is visible, False otherwise.
        """
        try:
            modal = self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".artdeco-modal")))
            logger.debug("Modal found and visible.")
            return modal.is_displayed()
        except TimeoutException:
            logger.debug("The '.artdeco-modal' not found or is not visible.")
            return False
        except Exception as e:
            logger.error(f"Error checking the modal: {e}", exc_info=True)
            return False

    def _fill_application_form(self, job: Job, max_attempts: int = 10) -> bool:
        """
        Fills out the application form step by step.

        :param job: The job object.
        :param max_attempts: The maximum number of attempts to fill the form.
        :return: True if form submission is successful, False otherwise.
        """
        logger.debug(f"Filling out application form for job: {job.title} at {job.company}")
        try:
            attempts = 0  # Initialize the attempt counter
            while attempts < max_attempts:
                self._2_fill_up(job)
                if self._2_next_or_submit():
                    logger.debug("Application form submitted successfully")
                    return True
                
                attempts += 1  # Increment the attempt counter
                logger.debug(f"Page {attempts} complete. Netx page.")

            logger.warning("Maximum attempts reached. Aborting application process.")
            utils.capture_screenshot(self.driver,"max_attempts_reached")
            return False  # Return false if the max attempts are reached

        except Exception as e:
            logger.error(f"An error occurred while filling the application form: {e}", exc_info=True)
            utils.capture_screenshot(self.driver,"error_in_fill_application_form")	
            return False

    def _2_next_or_submit(self) -> bool:
        """
        Clicks on 'Next', 'Review', or 'Submit' button in the application form.

        :return: True if application is submitted, False otherwise.
        """
        logger.debug("Starting attempt to click on 'Next', 'Review', or 'Submit'")
        try:
            buttons = self.driver.find_elements(By.CLASS_NAME, "artdeco-button--primary")
            logger.debug(f"Found {len(buttons)} primary buttons.")
            

            if not buttons:
                logger.error("No primary button found on the page.")
                utils.capture_screenshot(self.driver,"no_primary_buttons_found")
                return False

            # Prioritize 'Submit application'
            for button in buttons:
                button_text = button.text.strip().lower()
                if "submit application" in button_text:
                    logger.debug("Found 'Submit application' button.")
                    self._3_unfollow_company()
                    logger.debug("Clicking on the 'Submit application' button.")
                    button.click()
                    logger.debug("Clicked 'Submit application' button. Waiting for page update.")
                    self.wait.until(EC.staleness_of(button))
                    logger.debug("Application submitted successfully.")
                    return True

            # If 'Submit application' is not found, try 'Next' or 'Review'
            for button in buttons:
                button_text = button.text.strip().lower()
                if "next" in button_text or "review" in button_text:
                    logger.debug(f"Found '{button_text}' button.")
                    logger.debug(f"Clicking on the '{button.text.strip()}' button.")
                    button.click()
                    logger.debug(f"Clicked '{button_text}' button. Waiting for next section.")
                    time.sleep(1)
                    self._3_check_for_errors()
                    return False

            # No expected button found
            logger.error("No 'Submit application', 'Next', or 'Review' button was found.")
            # Print all buttons
            for button in buttons:
                button_text = button.text.strip().lower()
                logger.error(f"Button text: {button_text}")
            
            utils.capture_screenshot(self.driver,"no_submit_next_or_review_button_found")
            return False

        except Exception as e:
            logger.error(f"Error in the _2_next_or_submit function: {e}", exc_info=True)
            utils.capture_screenshot(self.driver,"error_in_2_next_or_submit")
            return False

    def _3_unfollow_company(self) -> None:
        """
        Unfollows the company to avoid staying updated with their page.
        """
        try:
            logger.debug("Unfollowing company to avoid staying updated with their page")
            follow_checkbox = self.wait.until(EC.element_to_be_clickable((By.XPATH,"//label[contains(.,'to stay up to date with their page.')]",)))
            follow_checkbox.click()
            logger.debug("Unfollowed company successfully")
        except TimeoutException:
            logger.warning("Unfollow checkbox not found within the timeout period, possibly already unfollowed")
            utils.capture_screenshot(self.driver,"unfollow_checkbox_timeout")
        except Exception as e:
            logger.warning(f"Failed to unfollow company: {e}", exc_info=True)

    def _3_check_for_errors(self) -> None:
        """
        Checks for form errors after clicking 'Next' or 'Review'.
        """
        logger.debug("Checking for form errors")
        try:
            error_elements = self.driver.find_elements(By.CLASS_NAME, "artdeco-inline-feedback--error")
            if error_elements:
                error_texts = [e.text for e in error_elements]
                logger.error(f"Form submission failed with errors: {error_texts}")
                raise Exception(f"Failed answering or file upload. {error_texts}")
            else:
                logger.debug("No form errors detected")
        except Exception as e:
            logger.error(f"Error while checking for form errors: {e}", exc_info=True)
            raise

    def _2_discard_application(self) -> None:
        """
        Discards the current application process.
        """
        logger.debug("Discarding application")
        try:
            dismiss_button = self.wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "artdeco-modal__dismiss")))
            dismiss_button.click()
            logger.debug("Clicked dismiss button on application modal")
            self.wait.until(EC.staleness_of(dismiss_button))

            confirm_buttons = self.driver.find_elements(By.CLASS_NAME, "artdeco-modal__confirm-dialog-btn")
            if confirm_buttons:
                self.wait.until(EC.element_to_be_clickable(confirm_buttons[0]))
                confirm_buttons[0].click()
                logger.debug("Confirmed discarding application")
                self.wait.until(EC.staleness_of(confirm_buttons[0]))
            else:
                logger.warning("Confirm discard button not found")
        except TimeoutException:
            logger.warning("Discard modal elements not found within the timeout period")
        except Exception as e:
            logger.warning(f"Failed to discard application: {e}", exc_info=True)

    def _2_fill_up(self, job: Job) -> None:
        """
        Fills up each section of the application form.

        :param job: The job object.
        """
        logger.debug(f"Starting to fill up form sections for job: {job.link}")

        try:
            # Find the Easy Apply content section
            try:
                easy_apply_content = self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "jobs-easy-apply-content")))
                logger.debug("Easy apply content section found successfully.")
            except TimeoutException:
                logger.warning("Easy apply content section not found. Attempting to submit the application directly.")
                return

            # Find all form sections within the Easy Apply content
            pb4_elements = easy_apply_content.find_elements(By.CLASS_NAME, "pb4")
            logger.debug(f"Found {len(pb4_elements)} form sections to process.")

            # Process each form section
            for index, element in enumerate(pb4_elements):
                logger.debug(f"Processing form section {index + 1}/{len(pb4_elements)}")
                self._3_process_form_element(element, job)
            logger.debug("All form sections processed successfully.")

        except TimeoutException:
            logger.error("Easy apply content section not found within the timeout period",exc_info=True,)
            raise
        except Exception as e:
            logger.error(f"An error occurred while filling up the form: {e}", exc_info=True)
            raise

    def _3_process_form_element(self, element: WebElement, job: Job) -> None:
        """
        Processes individual form elements.

        :param element: The form element to process.
        :param job: The job object.
        """
        logger.debug("Processing form element")
        if self._4_is_upload_field(element):
            self._4_handle_upload_fields(element, job)
        else:
            self._4_fill_additional_questions(element, job)

    def _4_is_upload_field(self, element: WebElement) -> bool:
        """
        Checks if the element is an upload field.

        :param element: The WebElement to check.
        :return: True if it's an upload field, False otherwise.
        """
        is_upload = bool(element.find_elements(By.XPATH, ".//input[@type='file']"))
        logger.debug(f"Element is upload field: {is_upload}")
        return is_upload

    def _4_handle_upload_fields(self, element: WebElement, job: Job) -> None:
        """
        Handles file upload fields in the application form, such as resumes and cover letters.
        Differentiates between PDF and HTML resumes to handle them appropriately.
        
        Args:
            element (WebElement): The WebElement representing the file upload field.
            job (Job): The job object containing job details.
        """
        logger.debug("Handling upload fields")

        # Attempt to click 'Show more resumes' button if it exists
        show_more_button_xpath = "//button[contains(@aria-label, 'Show') and contains(@aria-label, 'more resumes')]"
        try:
            show_more_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, show_more_button_xpath)))
            show_more_button.click()
            logger.debug("Clicked 'Show more resumes' button")
        except TimeoutException:
            logger.debug("'Show more resumes' button not found; proceeding with available upload fields")

        # Find all file upload elements
        file_upload_elements = self.driver.find_elements(By.XPATH, "//input[@type='file']")
        logger.debug(f"Found {len(file_upload_elements)} file upload elements")

        for file_element in file_upload_elements:
            # Make the file input visible if it's hidden
            self.driver.execute_script("arguments[0].classList.remove('hidden')", file_element)
            logger.debug("Made file upload element visible")

            # Determine if the upload field is for a resume or cover letter
            parent_text = file_element.find_element(By.XPATH, "..").text.lower()
            upload_type = self.gpt_answerer.resume_or_cover(parent_text)

            if "resume" in upload_type:
                logger.debug("Detected upload field for resume")
                if self.resume_path and Path(self.resume_path).is_file():
                    resume_extension = Path(self.resume_path).suffix.lower()
                    if resume_extension == '.pdf':
                        logger.debug("Resume is a PDF. Uploading directly.")
                        try:
                            file_element.send_keys(str(Path(self.resume_path).resolve()))
                            logger.info(f"Resume uploaded successfully from path: {self.resume_path}")
                        except Exception as e:
                            logger.error(f"Failed to upload PDF resume from path: {self.resume_path}", exc_info=True)
                            raise
                    elif resume_extension == '.html':
                        logger.debug("Resume is an HTML file. Generating and uploading PDF.")
                        try:
                            self._5_create_and_upload_resume(file_element, job)
                            logger.info("HTML resume converted to PDF and uploaded successfully.")
                        except Exception as e:
                            logger.error("Failed to create and upload the PDF from HTML resume.", exc_info=True)
                            raise
                    else:
                        logger.warning(f"Unsupported resume format: {resume_extension}. Skipping upload.")
                else:
                    logger.info("Resume path is invalid or not found; generating new resume.")
                    self._5_create_and_upload_resume(file_element, job)
            elif "cover" in upload_type:
                logger.debug("Detected upload field for cover letter. Uploading cover letter.")
                try:
                    self._5_create_and_upload_cover_letter(file_element, job)
                    logger.info("Cover letter uploaded successfully.")
                except Exception as e:
                    logger.error("Failed to create and upload the personalized cover letter.", exc_info=True)
                    raise
            else:
                logger.warning(f"Unexpected upload type detected: {upload_type}. Skipping field.")

        logger.debug("Finished handling upload fields")


    def render_resume_html(self, html_template: str, summary: str) -> str:
        """
        Renders the HTML resume template by replacing the placeholder with the personalized summary.
        
        Args:
            html_template (str): The HTML template of the resume.
            summary (str): The personalized summary to be inserted into the resume.
        
        Returns:
            str: The rendered HTML with the personalized summary.
        """
        template = Template(html_template)
        rendered_html = template.render(summary=summary)
        return rendered_html


    def generate_pdf_from_html(self, rendered_html: str, output_path: str) -> str:
        """
        Generates a PDF from the rendered HTML using WeasyPrint.
        
        Args:
            rendered_html (str): The rendered HTML content.
            output_path (str): The path where the PDF will be saved.
        
        Returns:
            str: The absolute path of the generated PDF.
        """
        try:
            # Create an HTML object from the HTML string
            html = HTML(string=rendered_html)
            
            # Generate the PDF and save to the specified path
            html.write_pdf(target=output_path)
            
            logger.debug(f"PDF generated and saved at: {output_path}")
            return os.path.abspath(output_path)
        except Exception as e:
            logger.error(f"Error generating PDF: {e}", exc_info=True)
            raise


    def _5_create_and_upload_resume(self, element: WebElement, job: Job) -> None:
        """
        Generates a personalized resume and uploads it to the application form.
        
        Args:
            element (WebElement): The WebElement of the upload field for the resume.
            job (Job): The job object containing job details.
        """
        logger.debug("Creating and uploading personalized resume.")
        try:
            # 0. Generate keywords from the job description
            keywords = self.gpt_answerer.extract_keywords_from_job_description(job.description)
            logger.debug(f"Keywords generated: {keywords}")
            
            # 1. Generate the personalized summary
            personalized_summary = self.gpt_answerer.generate_summary_based_on_keywords(
                USER_RESUME_CHATGPT, USER_RESUME_SUMMARY, keywords
            ) 
            logger.debug(f"Personalized summary: {personalized_summary}")

            # 2. Render the HTML with the personalized summary
            rendered_html = self.render_resume_html(USER_RESUME_HTML, personalized_summary)
            logger.debug("Resume HTML rendered with the personalized summary.")

            # 3. Set the path to save the PDF
            folder_path = "generated_cv"
            utils.ensure_directory(folder_path)

            # 4. Generate a more humanized filename with size limits
            datetime_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
            file_name = generate_humanized_filename(
                prefix="Resume",
                job_title=job.title,
                company_name=job.company,
                datetime_str=datetime_str
            )
            file_path_pdf = os.path.join(folder_path, file_name)

            # 5. Generate the PDF from the rendered HTML
            self.generate_pdf_from_html(rendered_html, file_path_pdf)

            # 6. Check the file size
            self._6_check_file_size(file_path_pdf, 2 * 1024 * 1024)  # 2 MB
            logger.debug(f"File size checked: {file_path_pdf}")

            # 7. Upload the PDF
            element.send_keys(os.path.abspath(file_path_pdf))
            job.pdf_path = os.path.abspath(file_path_pdf)
            time.sleep(2)
            logger.debug("Personalized resume uploaded successfully.")
        except Exception as e:
            logger.error("Failed to create and upload the personalized resume.", exc_info=True)
            utils.capture_screenshot(self.driver, "create_and_upload_resume_exception")
            raise

    def _5_create_and_upload_cover_letter(self, element: WebElement, job: Job) -> None:
        """
        Generates a personalized cover letter and uploads it to the application form.
        
        Args:
            element (WebElement): The WebElement of the upload field for the cover letter.
            job (Job): The job object containing job details.
        """
        logger.debug("Creating and uploading personalized cover letter.")
        try:
            # 0. Extract keywords from the job description
            keywords = self.gpt_answerer.extract_keywords_from_job_description(job.description)
            logger.debug(f"Keywords extracted for cover letter: {keywords}")
            
            # 1. Generate the tailored cover letter using keywords
            cover_letter = self.gpt_answerer.generate_cover_letter_based_on_keywords(
                job.description, USER_RESUME_HTML, keywords
            )
            logger.debug(f"Generated cover letter: {cover_letter}")
                       
            # 2. Set the path to save the PDF
            folder_path = "generated_cv"
            utils.ensure_directory(folder_path)

            # 3. Generate a more humanized filename with size limits
            datetime_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
            file_name = generate_humanized_filename(
                prefix="Cover_Letter",
                job_title=job.title,
                company_name=job.company,
                datetime_str=datetime_str
            )
            file_path_pdf = os.path.join(folder_path, file_name)

            # 4. Generate the PDF from the rendered HTML
            self._6_generate_pdf(file_path_pdf, cover_letter, "Cover Letter")
            logger.debug(f"Cover letter PDF generated at: {file_path_pdf}")

            # 5. Check the file size
            self._6_check_file_size(file_path_pdf, 2 * 1024 * 1024)  # 2 MB
            logger.debug(f"Cover letter file size is within the allowed limit: {file_path_pdf}")

            # 6. Upload the PDF
            element.send_keys(os.path.abspath(file_path_pdf))
            job.cover_letter_path = os.path.abspath(file_path_pdf)
            time.sleep(2)
            logger.debug("Personalized cover letter uploaded successfully.")
        
        except Exception as e:
            logger.error("Failed to create and upload the personalized cover letter.", exc_info=True)
            utils.capture_screenshot(self.driver, "create_and_upload_cover_letter_exception")
            raise

    def _6_generate_pdf(self, file_path_pdf: str, content: str, title: str) -> None:
        """
        Generates a PDF file with the specified content.
        
        Args:
            file_path_pdf (str): The path where the PDF will be saved.
            content (str): The textual content to include in the PDF.
            title (str): The title of the PDF document.
        """
        logger.debug(f"Generating PDF for: {title}")
        try:
            c = canvas.Canvas(file_path_pdf, pagesize=A4)
            styles = getSampleStyleSheet()
            style = styles['Normal']
            style.fontName = 'Helvetica'
            style.fontSize = 12
            style.leading = 15
            style.alignment = TA_JUSTIFY

            paragraph = Paragraph(content, style)
            frame = Frame(inch, inch, A4[0] - 2 * inch, A4[1] - 2 * inch, showBoundary=0)
            frame.addFromList([paragraph], c)
            c.save()
            logger.debug(f"PDF generated and saved at: {file_path_pdf}")
        except Exception as e:
            logger.error(f"Failed to generate PDF for {title}: {e}", exc_info=True)
            raise

    def _6_check_file_size(self, file_path: str, max_size: int) -> None:
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



    def _6_handle_http_error(self, error: HTTPStatusError) -> None:
        """
        Handles HTTP status errors during resume generation and determines
        the wait time from HTTP error headers.
        """
        if error.response.status_code == 429:
            retry_after = error.response.headers.get("retry-after")
            retry_after_ms = error.response.headers.get("retry-after-ms")

            if retry_after:
                wait_time = int(retry_after)
            elif retry_after_ms:
                wait_time = int(retry_after_ms) // 1000
            else:
                wait_time = 20  # Default wait time

            logger.warning(f"Rate limit exceeded, waiting {wait_time} seconds before retrying...")
            time.sleep(wait_time)
        else:
            logger.error("HTTP error occurred during resume generation", exc_info=True)
            raise

    def _4_fill_additional_questions(self, element: WebElement, job: Job) -> None:
        """
        Fills out additional questions in the application form.
        """
        logger.debug("Filling additional questions")
        try:
            form_sections = element.find_elements(By.CLASS_NAME, "jobs-easy-apply-form-section__grouping")
            if not form_sections:
                logger.debug("No form sections found in this element")
                return

            logger.debug(f"Found {len(form_sections)} additional form sections to process")
            for section in form_sections:
                self._5_process_form_section(section, job)
            logger.debug("All form sections processed successfully")
        except Exception as e:
            logger.warning("An error occurred while filling additional questions", exc_info=True)
            utils.capture_screenshot(self.driver,"additional_questions_error")
            raise

    def _5_process_form_section(self, section: WebElement, job: Job) -> None:
        """
        Processes a single form section and handles different types of questions.
        """
        logger.debug("Processing form section")
        
        if self._6_find_and_handle_typeahead_question(section, job): 
            return
        elif self._6_handle_terms_of_service(section):
            return
        elif self._6_find_and_handle_radio_question(section, job):
            return
        elif self._6_find_and_handle_textbox_question(section, job):
            return
        elif self._6_find_and_handle_date_question(section, job):
            return
        elif self._6_find_and_handle_dropdown_question(section, job):
            return
        else:
            logger.debug("No recognizable question type handled in this section")

    def _6_handle_terms_of_service(self, element: WebElement) -> bool:
        """
        Handles 'Terms of Service' checkbox in the form.
        """
        labels = element.find_elements(By.TAG_NAME, "label")
        if labels and any(
            term in labels[0].text.lower()
            for term in ["terms of service", "privacy policy", "terms of use"]
        ):
            try:
                self.wait.until(EC.element_to_be_clickable(labels[0])).click()
                logger.debug("Clicked terms of service checkbox")
                return True
            except Exception as e:
                logger.warning("Failed to click terms of service checkbox", exc_info=True)
        return False

    def _6_find_and_handle_radio_question(self, section: WebElement, job: Job) -> bool:
        """
        Finds and handles radio button questions in the form section.
        """
        logger.debug("Searching for radio questions")
        try:
            question_element = section.find_element(By.CLASS_NAME, "jobs-easy-apply-form-element")
            radios = question_element.find_elements(By.CLASS_NAME, "fb-text-selectable__option")
            if radios:
                question_text = section.text.lower()
                options = [radio.text.lower() for radio in radios]

                existing_answer = self._get_existing_answer(question_text, "radio")
                if existing_answer:
                    self._7_select_radio(radios, existing_answer)
                else:
                    answer = self.gpt_answerer.answer_question_from_options(question_text, options)
                    self._save_questions_to_json({"type": "radio", "question": question_text, "answer": answer})
                    self._7_select_radio(radios, answer)
                return True
        except Exception as e:
            logger.warning("Failed to handle radio question", exc_info=True)
        return False

    def _6_find_and_handle_textbox_question(self, section: WebElement, job: Job) -> bool:
        """
        Finds and handles textbox questions in the form section.
        """
        logger.debug("Searching for textbox questions")
        text_fields = section.find_elements(By.TAG_NAME, "input") + section.find_elements(By.TAG_NAME, "textarea")

        if text_fields:
            text_field = text_fields[0]
            label_elements = section.find_elements(By.TAG_NAME, "label")
            question_text = label_elements[0].text.lower().strip() if label_elements else "unknown"
            
            # Determina se o campo é numérico
            field_type = text_field.get_attribute("type").lower()
            field_id = text_field.get_attribute("id").lower()
            is_numeric = "numeric" in field_id or field_type == "number"
            question_type = "numeric" if is_numeric else "textbox"

            is_cover_letter = "cover letter" in question_text.lower()
            if is_cover_letter:
                answer = self.gpt_answerer.answer_question_simple(question_text, job, 1000)
            else:
                existing_answer = self._get_existing_answer(question_text, question_type)
                if existing_answer:
                    answer = existing_answer
                else:
                    if is_numeric:
                        answer = self.gpt_answerer.answer_question_numeric(question_text)
                    else:
                        answer = self.gpt_answerer.answer_question_simple(question_text, job=job)
                    self._save_questions_to_json({"type": question_type, "question": question_text, "answer": answer})

            self._7_enter_text(text_field, answer)
            logger.debug(f"Entered answer into the textbox:{text_field}, {answer}")
            return True

        logger.debug("No textbox questions found")
        return False

    def _6_find_and_handle_date_question(self, section: WebElement, job: Job) -> bool:
        """
        Finds and handles date input questions in the form section.
        """
        logger.debug("Searching for date questions")
        date_fields = section.find_elements(By.XPATH, ".//input[@placeholder='mm/dd/yyyy']")
        if not date_fields:
            date_fields = section.find_elements(By.XPATH, ".//input[@name='artdeco-date']")

        if date_fields:
            date_field = date_fields[0]
            label_elements = section.find_elements(By.TAG_NAME, "label")
            question_text = label_elements[0].text.strip() if label_elements else "unknown"

            # Check if the question is about Today's Date
            if "today's date" in question_text.lower():
                answer_text = datetime.today().strftime("%m/%d/%Y")
                logger.debug(f"Detected 'Today's Date' question. Using current date: {answer_text}")
            else:
                existing_answer = self._get_existing_answer(question_text, "date")
                if existing_answer:
                    answer_text = existing_answer
                else:
                    answer_date = self.gpt_answerer.answer_question_date(question_text)
                    answer_text = answer_date.strftime("%m/%d/%Y")
                    self._save_questions_to_json({"type": "date", "question": question_text, "answer": answer_text})

            self._7_enter_text(date_field, answer_text)
            logger.debug("Entered date answer")
            return True

        logger.debug("No date questions found")
        return False

    def _extract_question_text(self, section: WebElement) -> str:
        """
        Extracts the question text from a specific section of the form.

        The function attempts to retrieve the question text by searching for <label>
        elements, spans with a specific class, or using the section's full text as a fallback.

        Args:
            section (WebElement): The form section where the question is located.

        Returns:
            str: The question text or 'unknown' if extraction fails.
        """
        # Attempt to get text from <label> elements
        label_elements = section.find_elements(By.TAG_NAME, "label")
        if label_elements:
            return label_elements[0].text.strip()

        # Attempt to get text from spans with a specific class
        span_elements = section.find_elements(By.CLASS_NAME, "jobs-easy-apply-form-section__group-title")
        if span_elements:
            return span_elements[0].text.strip()

        # Fallback: use the section's full text
        section_text = section.text.strip()
        if section_text:
            return section_text

        # Return 'unknown' if none of the above options work
        return 'unknown'


    def _6_find_and_handle_dropdown_question(self, section: WebElement, job: Job) -> bool:
        """
        Searches for and handles dropdown questions within a form section.

        The function looks for <select> elements, ensures they are visible and clickable,
        extracts available options, checks for existing answers or generates new ones
        using the GPT assistant, and finally selects the appropriate option.

        Args:
            section (WebElement): The form section to be analyzed.
            job (Job): Object representing the current job posting.

        Returns:
            bool: True if a dropdown was found and handled successfully, False otherwise.
        """
        logger.debug("Starting search for dropdown questions in the section")

        try:
            # Search for <select> elements in the section
            dropdowns = section.find_elements(By.TAG_NAME, "select")
            if not dropdowns:
                logger.debug("No dropdown found in this section")
                return False

            dropdown = dropdowns[0]
            logger.debug("Dropdown found")

            # Ensure the dropdown is visible and clickable
            self.wait.until(EC.visibility_of(dropdown))
            self.wait.until(EC.element_to_be_clickable(dropdown))

            # Extract available options from the dropdown
            select = Select(dropdown)
            options = [option.text.strip() for option in select.options]
            logger.debug(f"Dropdown options obtained: {options}")

            # Extract the question text using the helper method
            question_text = self._extract_question_text(section)
            logger.debug(f"Question text identified: {question_text}")

            # Check if there is an existing answer stored for this question
            existing_answer = self._get_existing_answer(question_text, "dropdown")
            if existing_answer:
                logger.debug(f"Existing answer found: {existing_answer}")
                if existing_answer in options:
                    self._7_select_dropdown_option(dropdown, existing_answer)
                else:
                    logger.error(f"The answer '{existing_answer}' is not a valid option.")
                    raise ValueError(f"Invalid option selected: {existing_answer}")
            else:
                logger.debug("No existing answer found, generating answer with GPT")
                answer = self.gpt_answerer.answer_question_from_options(question_text, options)
                logger.debug(f"Answer generated: {answer}")
                self._save_questions_to_json({
                    "type": "dropdown",
                    "question": question_text,
                    "answer": answer
                })
                self._7_select_dropdown_option(dropdown, answer)

            logger.debug("Dropdown handled successfully")
            return True

        except Exception as e:
            logger.error(f"An error occurred while handling dropdown questions: {e}", exc_info=True)

        logger.debug("Exiting dropdown question handling without any action taken")
        return False

    def _6_find_and_handle_typeahead_question(self, section: WebElement, job: Job) -> bool:
        """
        Finds and handles typeahead questions in the form section.
        """
        logger.debug("Starting search for typeahead questions in the section")

        try:
            # Locate the input field with role 'combobox'
            logger.debug("Locating the typeahead input field...")
            typeahead_inputs = section.find_elements(By.XPATH, ".//input[@role='combobox']")
            if not typeahead_inputs:
                logger.debug("Typeahead field not found in this section")
                return False

            typeahead_input = typeahead_inputs[0]
            logger.debug("Typeahead field found")

            # Ensure the field is visible and clickable
            logger.debug("Waiting for the typeahead field to be visible and clickable...")
            self.wait.until(EC.visibility_of(typeahead_input))
            self.wait.until(EC.element_to_be_clickable(typeahead_input))

            # Get the question text from the label
            logger.debug("Extracting question text from the label...")
            labels = section.find_elements(By.TAG_NAME, "label")
            question_text = labels[0].text.strip() if labels else "unknown"
            logger.debug(f"Question text identified: {question_text}")

            # Check if there is already a saved answer
            existing_answer = self._get_existing_answer(question_text, "typeahead")
            if existing_answer:
                logger.debug(f"Existing answer found: {existing_answer}")
            else:
                logger.debug("No existing answer found, generating answer with GPT")
                # Generate answer using GPT
                existing_answer = self.gpt_answerer.answer_question_simple(question_text, job, 50)
                logger.debug(f"Answer generated for typeahead: {existing_answer}")
                self._save_questions_to_json({"type": "typeahead", "question": question_text, "answer": existing_answer})

            # Enter the text in the typeahead field
            logger.debug(f"Entering text in the typeahead field: {existing_answer}")
            typeahead_input.clear()
            typeahead_input.send_keys(existing_answer)
            time.sleep(1)

            # Wait for the suggestions to appear
            logger.debug("Waiting for suggestions after entering text in the typeahead...")
            suggestions_container_xpath = ".//div[contains(@class, 'basic-typeahead__triggered-content')]"
            suggestions_xpath = ".//div[contains(@class, 'basic-typeahead__selectable')]"

            try:
                suggestions_container = self.wait.until(
                    EC.visibility_of_element_located((By.XPATH, suggestions_container_xpath))
                )
                logger.debug("Suggestions container found")
                suggestions = suggestions_container.find_elements(By.XPATH, suggestions_xpath)
                if not suggestions:
                    logger.warning("No suggestions found after entering text in the typeahead")
                    return False

                first_suggestion = suggestions[0]
                logger.debug("First suggestion found, selecting it")
                self.driver.execute_script("arguments[0].scrollIntoView(true);", first_suggestion)
                first_suggestion.click()
                logger.debug("First suggestion successfully selected")
            except Exception as e:
                logger.warning(f"Error selecting the first suggestion: {e}", exc_info=True)
                # Try using keyboard events as an alternative
                logger.debug("Trying to select the suggestion using keyboard events")
                typeahead_input.send_keys(Keys.ARROW_DOWN)
                typeahead_input.send_keys(Keys.RETURN)

            # Confirm the selection
            selected_value = typeahead_input.get_attribute("value").strip()
            logger.debug(f"Selected value in typeahead: {selected_value}")

            return True

        except NoSuchElementException:
            logger.debug("Typeahead field not found in the section")
            return False
        except Exception as e:
            logger.error(f"An error occurred while handling typeahead questions: {e}", exc_info=True)
            return False

    def _7_enter_text(self, element: WebElement, text: str) -> None:
        """
        Enters text into a form field.
        """
        try:
            self.wait.until(EC.element_to_be_clickable(element))
            element.clear()
            element.send_keys(text)
        except Exception as e:
            logger.warning(f"Failed to enter text: {text}", exc_info=True)
            raise

    def _7_select_radio(self, radios: List[WebElement], answer: str) -> None:
        """
        Selects a radio button based on the answer.
        """
        logger.debug(f"Selecting radio option: {answer}")
        for radio in radios:
            if answer.lower() in radio.text.lower():
                try:
                    label = radio.find_element(By.TAG_NAME, "label")
                    self.wait.until(EC.element_to_be_clickable(label)).click()
                    logger.debug(f"Radio option '{answer}' selected")
                    return
                except Exception as e:
                    logger.warning(f"Failed to click radio option '{answer}'", exc_info=True)
        logger.warning(f"Answer '{answer}' not found; selecting the last available option")
        self.wait.until(EC.element_to_be_clickable(radios[-1].find_element(By.TAG_NAME, "label"))).click()

    def _7_select_dropdown_option(self, element: WebElement, text: str) -> None:
        try:
            logger.debug(f"Selecting dropdown option: {text}")
            select = Select(element)
            options = [option.text.strip() for option in select.options]
            if text in options:
                select.select_by_visible_text(text)
                logger.debug(f"Dropdown option '{text}' selected successfully")
                
                # Wait for the selection to be updated
                selected_option = select.first_selected_option.text.strip()
                assert selected_option == text, f"Expected '{text}', but selected '{selected_option}'"
                logger.debug(f"Confirmation: '{selected_option}' was successfully selected.")
                time.sleep(0.5)
            else:
                logger.warning(f"Option '{text}' not found in dropdown. Available options: {options}")
                raise ValueError(f"Option '{text}' not found in dropdown.")
        except AssertionError as ae:
            logger.error(f"AssertionError: {ae}", exc_info=True)
            raise
        except Exception as e:
            logger.warning(f"Failed to select dropdown option '{text}'", exc_info=True)
            raise

# Json

    def _save_questions_to_json(self, question_data: dict) -> None:
        """
        Saves the question and answer to a JSON file for future reuse only if the question is not a duplicate.
        """
        output_dir = Path("data_folder/output")
        output_file = output_dir / "answers.json"
        sanitized_question = self.utils_sanitize_text(question_data["question"])
        question_data["question"] = sanitized_question
        logger.debug(f"Attempting to save question data to JSON: {question_data}")
        
        try:
            # Ensure the directory exists
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Directory verified or created: {output_dir}")
            
            if output_file.exists():
                with output_file.open("r", encoding="utf-8") as f:
                    try:
                        data = json.load(f)
                        if not isinstance(data, list):
                            logger.error("The JSON file format is incorrect. Expected a list of questions.")
                            raise ValueError("The JSON file format is incorrect. Expected a list of questions.")
                    except json.JSONDecodeError:
                        logger.warning("JSON file is empty or invalid. Initializing with an empty list.")
                        data = []
            else:
                data = []
                logger.info(f"JSON file not found. Creating new file: {output_file}")
            
            # Check if the question already exists
            if any(self.utils_sanitize_text(item["question"]) == sanitized_question for item in data):
                logger.debug(f"Question already exists and will not be saved again: {sanitized_question}")
                return  # Do not save duplicates
            
            # Add the new question
            data.append(question_data)
            
            with output_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            logger.debug("Question data successfully saved to JSON")
        
        except Exception as e:
            logger.error("Error saving question data to JSON file", exc_info=True)
            raise

    def _load_questions_from_json(self) -> List[dict]:
        """
        Loads previously answered questions from a JSON file to reuse answers.
        """
        output_file = Path("data_folder/output") / "answers.json"
        logger.debug(f"Loading questions from JSON file: {output_file}")
        try:
            if not output_file.exists():
                logger.warning(f"JSON file not found: {output_file}. Creating an empty file.")
                # Ensure the directory exists
                output_file.parent.mkdir(parents=True, exist_ok=True)
                # Create the file with an empty list
                with output_file.open("w", encoding="utf-8") as f:
                    json.dump([], f, indent=4, ensure_ascii=False)
                return []
            
            with output_file.open("r", encoding="utf-8") as f:
                try:
                    content = f.read().strip()
                    if not content:
                        logger.debug("JSON file is empty. Returning an empty list.")
                        return []
                    data = json.loads(content)
                    if not isinstance(data, list):
                        logger.error("The JSON file format is incorrect. Expected a list of questions.")
                        raise ValueError("The JSON file format is incorrect. Expected a list of questions.")
                except json.JSONDecodeError:
                    logger.warning("JSON decoding failed. Returning an empty list.")
                    return []
            
            logger.debug("Questions successfully loaded from JSON")
            return data
        except Exception as e:
            logger.error("Error loading question data from JSON file", exc_info=True)
            raise

    def _get_existing_answer(self, question_text: str, question_type: str) -> Optional[str]:
        """
        Retrieves an existing answer from the saved data based on the question text and type.
        """
        sanitized_question = self.utils_sanitize_text(question_text)
        return next(
            (
                item.get("answer") 
                for item in self.all_questions
                if self.utils_sanitize_text(item.get("question", "")) == sanitized_question 
                and item.get("type") == question_type
            ),
            None
        )

# Utils

    def utils_sanitize_text(self, text: str) -> str:
        """
        Sanitizes the input text by lowering case, stripping whitespace, and removing unwanted characters.
        """
        sanitized_text = text.lower().strip()
        sanitized_text = re.sub(r'[\"\\\n\r]', ' ', sanitized_text)
        sanitized_text = sanitized_text.rstrip(",")
        sanitized_text = re.sub(r"[\x00-\x1F\x7F]", "", sanitized_text)
        sanitized_text = re.sub(r'\s+', ' ', sanitized_text)
        # logger.debug(f"Sanitized text: {sanitized_text}")
        return sanitized_text
    
    
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