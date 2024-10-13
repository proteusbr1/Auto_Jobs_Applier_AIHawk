# aihawk_easy_applier.py

import base64
import json
import os
import re
import time
from typing import List, Optional, Any, Tuple, Dict
from datetime import datetime
from pathlib import Path

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
    MINIMUM_SCORE_JOB_APPLICATION,
    USER_RESUME_SUMMARY,
    USE_JOB_SCORE,
)
import src.utils as utils
from src.llm.llm_manager import GPTAnswerer
from loguru import logger
from src.job import Job


class AIHawkEasyApplier:
    """
    Automates the process of applying to jobs on LinkedIn using the 'Easy Apply' feature.
    """

    def __init__(
        self,
        driver: Any,
        resume_dir: Optional[str],
        set_old_answers: List[Tuple[str, str, str]],
        gpt_answerer: GPTAnswerer,
        resume_generator_manager,
        wait_time: int = 10,
    ):
        logger.debug("Initializing AIHawkEasyApplier")
        if resume_dir is None or not os.path.exists(resume_dir):
            logger.warning(
                "Provided resume_dir is None or does not exist. Setting resume_path to None."
            )
            resume_dir = None
        self.driver = driver
        self.wait = WebDriverWait(self.driver, wait_time)
        self.resume_path = resume_dir
        self.set_old_answers = set_old_answers
        self.gpt_answerer = gpt_answerer
        self.resume_generator_manager = resume_generator_manager
        self.all_questions = self._load_questions_from_json()

        logger.debug("AIHawkEasyApplier initialized successfully")

    def main_job_apply(self, job: Job) -> bool:
        """
        Main method to apply for a job.

        :param job: The job object containing job details.
        :return: True if application is successful, False otherwise.
        """
        logger.debug(f"Open job: {job.link}")

        if job is None:
            logger.error("Job object is None. Cannot apply.")
            return False

        # Set up the job in GPTAnswerer before any evaluation or form filling
        self.gpt_answerer.set_job(
            title=job.title,
            company=job.company,
            location=job.location,
            link=job.link,
            apply_method=job.apply_method,
            description=job.description,
            recruiter_link=job.recruiter_link,
        )
        logger.debug("Job set in GPTAnswerer successfully.")

        try:
            self.driver.get(job.link)
            self._check_for_premium_redirect(job)
            job.description = self._get_job_description()
            # job.recruiter_link = self._get_job_recruiter()

            if USE_JOB_SCORE:
                logger.debug("Evaluating job score using GPT.")
                if job.score is None:
                    job.score = self.gpt_answerer.evaluate_job(job, USER_RESUME_SUMMARY)
                    logger.debug(f"Job score is: {job.score}")
                    utils.write_to_file(job, "job_score")

                if job.score < MINIMUM_SCORE_JOB_APPLICATION:
                    logger.info(f"Score is {job.score}. Skipping application.")
                    return False
                else:
                    logger.info(f"Score is {job.score}. Proceeding with the application.")

            try:
                easy_apply_button = self._find_easy_apply_button(job)
            except Exception as e:
                logger.error(f"Failed to find 'Easy Apply' button: {e}", exc_info=True)
                return False

            if easy_apply_button:
                # Click the 'Easy Apply' button
                ActionChains(self.driver).move_to_element(easy_apply_button).click().perform()
                logger.debug("'Easy Apply' button clicked successfully")

                # Handle potential modals that may obstruct the button
                self._handle_job_search_safety_reminder()

                # Apply for the job
                success = self._fill_application_form(job)
                if success:
                    logger.debug(
                        f"Job application process completed successfully for job: {job.title} at {job.company}"
                    )
                    return True
                else:
                    logger.warning(
                        f"Job application process failed for job: {job.title} at {job.company}"
                    )
                    return False
            else:
                logger.warning(
                    f"'Easy Apply' button not found for job: {job.title} at {job.company}"
                )
                return False

        except Exception as e:
            logger.error(f"Failed to apply for the job: {e}")
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
                see_more_button = self.wait.until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            '//button[@aria-label="Click to see more description"]',
                        )
                    )
                )
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
            raise Exception(
                "Timed out waiting for the job description element"
            ) from te
        except Exception as e:
            logger.warning(
                f"Unexpected error in _get_job_description: {e}", exc_info=True
            )
            raise Exception("Error getting job description") from e

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

    def _find_easy_apply_button(self, job: Any) -> Optional[WebElement]:
        """
        Find the 'Easy Apply' button on the job page.

        :param job: The job object.
        :return: The 'Easy Apply' button element if found.
        """
        logger.debug("Starting search for 'Easy Apply' button.")
        search_methods = [
            {
                "description": "Unique attribute 'Easy Apply' button",
                "xpath": '//button[contains(@aria-label, "Easy Apply")]',
            },
            {
                "description": "Button with specific class",
                "xpath": '//button[contains(@class, "jobs-apply-button") and contains(text(), "Easy Apply")]',
            },
            {
                "description": "Button by alternate text",
                "xpath": '//button[text()="Easy Apply" or text()="Apply Now"]',
            },
            {
                "description": "'Easy Apply' button with data-test",
                "xpath": '//button[@data-test="easy-apply-button"]',
            },
        ]

        max_attempts = 1
        for attempt in range(max_attempts):
            logger.debug(f"Attempt {attempt + 1} to find the 'Easy Apply' button.")
            self._check_for_premium_redirect(job)
            self._2_scroll_page()

            for method in search_methods:
                try:
                    logger.debug(f"Using search method: {method['description']}")
                    buttons = self._2_find_buttons_by_xpath(method["xpath"])
                    for button in buttons:
                        if self._2_is_element_clickable(button):
                            logger.debug(
                                f"'Easy Apply' button found using {method['description']}."
                            )
                            return button
                except Exception as e:
                    logger.warning(
                        f"Error using search method {method['description']}: {e}",
                        exc_info=True,
                    )

            if attempt < max_attempts - 1:
                logger.debug("Refreshing the page to try to find the 'Easy Apply' button again.")
                self.driver.refresh()
                try:
                    self.wait.until(EC.presence_of_element_located((By.XPATH, "//button")))
                    logger.debug("Page refreshed and buttons reloaded.")
                except TimeoutException as te:
                    logger.warning("Timeout waiting for buttons to load after refresh.")

        logger.error("No clickable 'Easy Apply' button found after multiple attempts.")
        raise Exception("No clickable 'Easy Apply' button found.")

    def _2_scroll_page(self) -> None:
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

    def _2_find_buttons_by_xpath(self, xpath: str) -> List[WebElement]:
        """
        Finds multiple buttons based on the provided XPath.

        :param xpath: The XPath to locate buttons.
        :return: A list of WebElements found.
        """
        logger.debug(f"Searching for buttons with XPath: {xpath}")
        return self.wait.until(lambda d: d.find_elements(By.XPATH, xpath))

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

    def _handle_job_search_safety_reminder(self) -> None:
        """
        Handles the 'Job search safety reminder' modal if it appears.
        """
        try:
            modal = self.wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, "artdeco-modal"))
            )
            logger.debug("Job search safety reminder modal detected.")
            continue_button = modal.find_element(
                By.XPATH, '//button[contains(., "Continue applying")]'
            )
            if continue_button:
                continue_button.click()
                logger.debug("Clicked 'Continue applying' button in modal.")
        except NoSuchElementException:
            logger.debug("Job search safety reminder elements not found.")
        except TimeoutException:
            logger.debug("No 'Job search safety reminder' modal detected.")
        except Exception as e:
            logger.warning(
                f"Unexpected error while handling safety reminder modal: {e}",
                exc_info=True,
            )

    def _fill_application_form(self, job: Job, max_attempts: int = 5) -> bool:
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
            return False  # Return false if the max attempts are reached

        except Exception as e:
            logger.error(f"An error occurred while filling the application form: {e}", exc_info=True)
            # self._2_discard_application()
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
                self.utils_capture_screenshot("no_primary_buttons_found")
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
            
            self.utils_capture_screenshot("no_submit_next_or_review_button_found")
            return False

        except Exception as e:
            logger.error(f"Error in the _2_next_or_submit function: {e}", exc_info=True)
            self.utils_capture_screenshot("error_in_2_next_or_submit")
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
        logger.debug(f"Starting to fill up form sections for job: {job.title} at {job.company}")

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
                logger.debug("Uploading resume")
                if self.resume_path and Path(self.resume_path).is_file():
                    try:
                        file_element.send_keys(str(Path(self.resume_path).resolve()))
                        logger.debug(f"Resume uploaded from path: {self.resume_path}")
                    except Exception as e:
                        logger.error(f"Failed to upload resume from path: {self.resume_path}", exc_info=True)
                        raise
                else:
                    logger.warning("Resume path is invalid or not found; generating new resume")
                    self._5_create_and_upload_resume(file_element, job)
            elif "cover" in upload_type:
                logger.debug("Uploading cover letter")
                self._5_create_and_upload_cover_letter(file_element, job)
            else:
                logger.warning(f"Unexpected output from resume_or_cover: {upload_type}")

        logger.debug("Finished handling upload fields")

    def _5_create_and_upload_resume(self, element: WebElement, job: Job) -> None:
        """
        Generates a resume and uploads it to the application form.
        """
        logger.debug("Creating and uploading resume")
        folder_path = "generated_cv"
        self.utils_ensure_directory(folder_path)

        try:
            timestamp = int(time.time())
            file_name = f"CV_{timestamp}.pdf"
            file_path_pdf = os.path.join(folder_path, file_name)
            self.utils_ensure_directory(folder_path)

            # Generate resume PDF content
            resume_pdf_base64 = self.resume_generator_manager.pdf_base64(job_description_text=job.description)
            with open(file_path_pdf, "wb") as f:
                f.write(base64.b64decode(resume_pdf_base64))

            # Check file size
            self._6_check_file_size(file_path_pdf, 2 * 1024 * 1024)  # 2 MB
            logger.debug(f"Uploading resume from path: {file_path_pdf}")

            # Upload the resume
            element.send_keys(os.path.abspath(file_path_pdf))
            job.pdf_path = os.path.abspath(file_path_pdf)
            time.sleep(2)
            logger.debug(f"Resume uploaded successfully from: {file_path_pdf}")
        except HTTPStatusError as e:
            self._6_handle_http_error(e)
        except Exception as e:
            logger.error("Resume upload failed", exc_info=True)
            self.utils_capture_screenshot(f"resume_upload_exception_{timestamp}")
            raise Exception("Upload failed.") from e

    def _5_create_and_upload_cover_letter(self, element: WebElement, job: Job) -> None:
        """
        Generates a cover letter and uploads it to the application form.
        """
        logger.debug("Creating and uploading cover letter")
        cover_letter_text = self.gpt_answerer.answer_question_textual_wide_range("Write a cover letter", job=job)
        folder_path = "generated_cv"
        self.utils_ensure_directory(folder_path)

        try:
            timestamp = int(time.time())
            file_name = f"Cover_Letter_{timestamp}.pdf"
            file_path_pdf = os.path.join(folder_path, file_name)
            self.utils_ensure_directory(folder_path)

            # Generate cover letter PDF
            self._6_generate_pdf(file_path_pdf, cover_letter_text, "Cover Letter")
            self._6_check_file_size(file_path_pdf, 2 * 1024 * 1024)  # 2 MB
            logger.debug(f"Uploading cover letter from: {file_path_pdf}")

            # Upload the cover letter
            element.send_keys(os.path.abspath(file_path_pdf))
            job.cover_letter_path = os.path.abspath(file_path_pdf)
            time.sleep(2)
            logger.debug("Cover letter uploaded successfully")
        except HTTPStatusError as e:
            self._6_handle_http_error(e)
        except Exception as e:
            logger.error("Cover letter upload failed", exc_info=True)
            self.utils_capture_screenshot("cover_letter_upload_exception")
            raise Exception("Upload failed.") from e

    def _6_generate_pdf(self, file_path_pdf: str, content: str, title: str) -> None:
        """
        Generates a PDF file with the specified content.
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
            logger.error(f"Failed to generate PDF for {title}", exc_info=True)
            raise

    def _6_check_file_size(self, file_path: str, max_size: int) -> None:
        """
        Checks if the file size is within the specified limit.
        """
        file_size = os.path.getsize(file_path)
        logger.debug(f"File size: {file_size} bytes")
        if file_size > max_size:
            logger.error(f"File size exceeds limit of {max_size} bytes: {file_size} bytes")
            raise ValueError("File size exceeds the maximum limit.")

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
            self.utils_capture_screenshot("additional_questions_error")
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
                answer = self.gpt_answerer.answer_question_textual_wide_range(question_text, job=job)
            else:
                existing_answer = self._get_existing_answer(question_text, question_type)
                if existing_answer:
                    answer = existing_answer
                else:
                    if is_numeric:
                        answer = self.gpt_answerer.answer_question_numeric(question_text)
                    else:
                        answer = self.gpt_answerer.answer_question_textual_wide_range(question_text, job=job)
                    self._save_questions_to_json({"type": question_type, "question": question_text, "answer": answer})

            self._7_enter_text(text_field, answer)
            logger.debug("Entered answer into the textbox")
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

    def _6_find_and_handle_dropdown_question(self, section: WebElement, job: Job) -> bool:
        """
        Finds and handles dropdown questions in the form section.
        """
        logger.debug("Starting search for dropdown questions in the section")

        try:
            # Look for the <select> element
            dropdowns = section.find_elements(By.TAG_NAME, "select")
            if not dropdowns:
                logger.debug("No dropdown found in this section")
                return False

            if dropdowns:
                dropdown = dropdowns[0]
                logger.debug("Dropdown found")

                # Ensure the dropdown is visible and enabled
                self.wait.until(EC.visibility_of(dropdown))
                self.wait.until(EC.element_to_be_clickable(dropdown))

                # Get the options from the dropdown
                select = Select(dropdown)
                options = [option.text.strip() for option in select.options]
                logger.debug(f"Dropdown options obtained: {options}")

                # Get the question text
                label_elements = section.find_elements(By.TAG_NAME, "label")
                question_text = label_elements[0].text.strip() if label_elements else "unknown"
                logger.debug(f"Question text identified: {question_text}")

                # Check if there is already a saved answer
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
                    self._save_questions_to_json({"type": "dropdown", "question": question_text, "answer": answer})
                    self._7_select_dropdown_option(dropdown, answer)

                return True
            else:
                logger.debug("No dropdown found in the section.")
                return False

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
                existing_answer = self.gpt_answerer.answer_question_textual_wide_range(question_text, job)
                logger.debug(f"Answer generated for typeahead: {existing_answer}")
                self._save_questions_to_json({"type": "typeahead", "question": question_text, "answer": existing_answer})

            # Enter the text in the typeahead field
            logger.debug(f"Entering text in the typeahead field: {existing_answer}")
            typeahead_input.clear()
            typeahead_input.send_keys(existing_answer)
            time.sleep(1)  # Wait a bit for the suggestions to load

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
        Saves the question and answer to a JSON file for future reuse only if the question is not duplicated.
        """
        output_file = Path("data_folder/output") / "answers.json"
        sanitized_question = self.utils_sanitize_text(question_data["question"])
        question_data["question"] = sanitized_question
        logger.debug(f"Attempting to save question data to JSON: {question_data}")
        
        try:
            if output_file.exists():
                with output_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not isinstance(data, list):
                        logger.error("JSON file format is incorrect. Expected a list of questions.")
                        raise ValueError("JSON file format is incorrect. Expected a list of questions.")
            else:
                data = []
            
            # Check if the question already exists
            if any(self.utils_sanitize_text(item["question"]) == sanitized_question for item in data):
                logger.debug(f"Question already exists and will not be saved: {sanitized_question}")
                return  # Do not save duplicates
            
            # Append the new question
            data.append(question_data)
            
            with output_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            logger.debug("Question data saved successfully to JSON")
            
        except Exception as e:
            logger.error("Error saving questions data to JSON file", exc_info=True)
            raise

    def _load_questions_from_json(self) -> List[dict]:
        """
        Load previously answered questions from a JSON file to reuse answers.
        """
        output_file = Path("data_folder/output") / "answers.json"
        logger.debug(f"Loading questions from JSON file: {output_file}")
        try:
            with output_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    logger.error("JSON file format is incorrect. Expected a list of questions.")
                    raise ValueError("JSON file format is incorrect. Expected a list of questions.")
            
            logger.debug("Questions loaded successfully from JSON")
            return data
        except FileNotFoundError:
            logger.warning("JSON file not found, returning empty list")
            return []
        except json.JSONDecodeError:
            logger.exception("JSON decoding failed, returning empty list")
            return []
        except Exception as e:
            logger.exception("Error loading questions data from JSON file")
            raise

    def _get_existing_answer(self, question_text: str, question_type: str) -> Optional[str]:
        """
        Retrieves an existing answer from saved data based on the question text and type.
        """
        sanitized_question = self.utils_sanitize_text(question_text)
        return next(
            (item.get("answer") for item in self.all_questions
            if self.utils_sanitize_text(item.get("question", "")) == sanitized_question and item.get("type") == question_type),
            None
        )

# Utils

    def utils_ensure_directory(self, folder_path: str) -> None:
        """
        Ensures that the specified directory exists.
        """
        try:
            os.makedirs(folder_path, exist_ok=True)
            logger.debug(f"Directory ensured at path: {folder_path}")
        except Exception as e:
            logger.error(f"Failed to create directory: {folder_path}", exc_info=True)
            raise

    def utils_capture_screenshot(self, name: str) -> None:
        """
        Captures a screenshot of the current browser window.
        """
        try:
            screenshots_dir = "screenshots"
            self.utils_ensure_directory(screenshots_dir)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(screenshots_dir, f"{name}_{timestamp}.png")
            success = self.driver.save_screenshot(file_path)
            if success:
                logger.debug(f"Screenshot saved at: {file_path}")
            else:
                logger.warning("Failed to save screenshot")
        except Exception as e:
            logger.error("An error occurred while capturing the screenshot", exc_info=True)

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

#No Used Yet

    def navigate_date_picker(self, month_name: str, year: int) -> None:
        logger.debug(f"Navigating date picker to {month_name} {year}")
        # Locate the calendar header elements
        while True:
            calendar_header = self.driver.find_element(By.CLASS_NAME, 'artdeco-calendar__month')
            current_month_year = calendar_header.text
            if current_month_year == f"{month_name} {year}":
                logger.debug("Reached the desired month and year in the date picker.")
                break
            else:
                # Click the next month button
                next_month_button = self.driver.find_element(By.XPATH, "//button[@data-calendar-next-month='']")
                next_month_button.click()
                time.sleep(0.5)  # Wait for the calendar to update

    def select_date_in_picker(self, day: int) -> None:
        logger.debug(f"Selecting day {day} in date picker.")
        day_buttons = self.driver.find_elements(By.XPATH, f"//button[@data-calendar-day='' and text()='{day}']")
        if day_buttons:
            day_buttons[0].click()
            logger.debug(f"Clicked on day {day} in date picker.")
        else:
            logger.warning(f"Day {day} not found in date picker.")

    def handle_dropdown_fields(self, element: WebElement) -> None:
        """
        No Used Yet
        """
        logger.debug("Handling dropdown fields")

        dropdown = element.find_element(By.TAG_NAME, "select")
        select = Select(dropdown)

        options = [option.text for option in select.options]
        logger.debug(f"Dropdown options found: {options}")

        parent_element = dropdown.find_element(By.XPATH, "../..")

        label_elements = parent_element.find_elements(By.TAG_NAME, "label")
        if label_elements:
            question_text = label_elements[0].text.lower()
        else:
            question_text = "unknown"

        logger.debug(f"Detected question text: {question_text}")

        existing_answer = None
        for item in self.all_questions:
            if (
                self.utils_sanitize_text(question_text) in item["question"]
                and item["type"] == "dropdown"
            ):
                existing_answer = item["answer"]
                break

        if existing_answer:
            logger.debug(
                f"Found existing answer for question '{question_text}': {existing_answer}"
            )
        else:
            logger.debug(
                f"No existing answer found, querying model for: {question_text}"
            )
            existing_answer = self.gpt_answerer.answer_question_from_options(
                question_text, options
            )
            logger.debug(f"Model provided answer: {existing_answer}")
            self._save_questions_to_json(
                {"type": "dropdown", "question": question_text, "answer": existing_answer}
            )

        if existing_answer in options:
            select.select_by_visible_text(existing_answer)
            logger.debug(f"Selected option: {existing_answer}")
        else:
            logger.error(
                f"Answer '{existing_answer}' is not a valid option in the dropdown"
            )
            raise ValueError(f"Invalid option selected: {existing_answer}")