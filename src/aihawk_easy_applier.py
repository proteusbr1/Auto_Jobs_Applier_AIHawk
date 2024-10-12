import base64
import json
import os
import re
import time
from typing import List, Optional, Any, Tuple
import traceback

from httpx import HTTPStatusError
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Frame, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_JUSTIFY
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
from pathlib import Path

from app_config import MINIMUM_SCORE_JOB_APPLICATION, USER_RESUME_SUMMARY, USE_JOB_SCORE
import src.utils as utils
from src.llm.llm_manager import GPTAnswerer
from loguru import logger
from src.job import Job


class AIHawkEasyApplier:
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
        self.all_data = self._load_questions_from_json()

        logger.debug("AIHawkEasyApplier initialized successfully")

    def _load_questions_from_json(self) -> List[dict]:
        output_file = "answers.json"
        logger.debug(f"Loading questions from JSON file: {output_file}")
        try:
            with open(output_file, "r") as f:
                try:
                    data = json.load(f)
                    if not isinstance(data, list):
                        logger.error(
                            "JSON file format is incorrect. Expected a list of questions."
                        )
                        raise ValueError(
                            "JSON file format is incorrect. Expected a list of questions."
                        )
                except json.JSONDecodeError:
                    logger.exception("JSON decoding failed")
                    data = []
            logger.debug("Questions loaded successfully from JSON")
            return data
        except FileNotFoundError:
            logger.warning("JSON file not found, returning empty list")
            return []
        except Exception as e:
            logger.exception("Error loading questions data from JSON file")
            raise Exception("Error loading questions data from JSON file") from e

    def check_for_premium_redirect(self, job: Any, max_attempts=3):
        current_url = self.driver.current_url
        attempts = 0

        while "linkedin.com/premium" in current_url and attempts < max_attempts:
            logger.warning(
                "Redirected to AIHawk Premium page. Attempting to return to job page."
            )
            attempts += 1

            self.driver.get(job.link)
            try:
                self.wait.until(
                    EC.url_to_be(job.link)
                )  # Wait until the URL is the job link
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
                f"Redirected to AIHawk Premium page and failed to return after {max_attempts} attempts. Job application aborted."
            )

    def job_apply(self, job: Job):
        logger.debug(f"Open job: {job.link}")

        if job is None:
            logger.error("Job object is None. Cannot apply.")
            raise ValueError("Job object is None. Cannot apply")
        
        # Set the job in GPTAnswerer before any evaluations or form filling
        self.gpt_answerer.set_job(
            title=job.title,
            company=job.company,
            location=job.location,
            link=job.link,
            apply_method=job.apply_method,
            description=job.description
        )
        logger.debug("Job set in GPTAnswerer successfully.")

        try:
            self.driver.get(job.link)
            self.check_for_premium_redirect(job)
            job.description = self._get_job_description()         

            if USE_JOB_SCORE:
                logger.debug("Evaluating job score using GPT.")
                if job.score is None:
                    job.score = self.gpt_answerer.evaluate_job(
                        job, USER_RESUME_SUMMARY
                    )
                    logger.debug(f"Job score is: {job.score}")
                    utils.write_to_file(job, "job_score")
                
                if job.score < MINIMUM_SCORE_JOB_APPLICATION:
                    logger.debug(f"Score is {job.score}. Skipping application.")
                    return False
                else:
                    logger.debug(f"Score is {job.score}. Proceeding with the application.")

            try:
                easy_apply_button = self._find_easy_apply_button(job)
            except Exception as e:
                logger.error(f"Failed to find 'Easy Apply' button: {e}", exc_info=True)
                return False

            if easy_apply_button:
                # Click the 'Easy Apply' button
                logger.debug("Easy Apply button found. Attempting to click.")
                ActionChains(self.driver).move_to_element(easy_apply_button).click().perform()
                logger.debug("'Easy Apply' button clicked successfully")
                
                # Handle potential modals that might obstruct the button
                self._handle_job_search_safety_reminder()
                
                # Apply for the job
                self._fill_application_form(job)
                logger.debug(f"Job application process completed successfully for job: {job.title} at {job.company}")
                return True
            else:
                logger.warning(f"'Easy Apply' button not found for job: {job.title} at {job.company}")
                return False

        except Exception as e:
            logger.error(f"Failed to apply for the job: {e}")
            raise

    def _find_easy_apply_button(self, job: Any) -> Optional[WebElement]:
        logger.debug("Starting search for 'Easy Apply' button.")
        search_methods = [
            {
                "description": "Find all 'Easy Apply' buttons using find_elements",
                "find_elements": True,
                "xpath": '//button[contains(@class, "jobs-apply-button") and contains(., "Easy Apply")]',
            },
            {
                "description": "'aria-label' containing 'Easy Apply to'",
                "xpath": '//button[contains(@aria-label, "Easy Apply to")]',
            },
            {
                "description": "Button text search for 'Easy Apply' or 'Apply now'",
                "xpath": '//button[contains(text(), "Easy Apply") or contains(text(), "Apply now")]',
            },
        ]

        max_attempts = 2
        for attempt in range(max_attempts):
            logger.debug(f"Attempt {attempt + 1} to find 'Easy Apply' button.")
            self.check_for_premium_redirect(job)
            self._scroll_page()

            for method in search_methods:
                try:
                    logger.debug(f"Using search method: {method['description']}")
                    if method.get("find_elements"):
                        buttons = self._find_buttons_by_xpath(method["xpath"])
                        for index, button in enumerate(buttons):
                            if self._is_element_clickable(button):
                                logger.debug(f"'Easy Apply' button found using {method['description']} (Button {index + 1}).")
                                return button
                            else:
                                logger.warning(f"'Easy Apply' button {index + 1} found but not clickable.")
                    else:
                        button = self._find_single_button(method["xpath"])
                        if self._is_element_clickable(button):
                            logger.debug(f"'Easy Apply' button found using {method['description']}.")
                            return button
                except NoSuchElementException as e:
                    logger.warning(f"'Easy Apply' button not found using method: {method['description']}")
                    logger.warning(f"Página atual HTML: {self.driver.page_source}")
                except TimeoutException as te:
                    logger.warning    (f"Timed out using search method: {method['description']}")
                    logger.warning(f"Página atual HTML: {self.driver.page_source}")
                except Exception as e:
                    logger.warning(f"Error using search method {method['description']}: {e}", exc_info=True)
                    logger.warning(f"Página atual HTML: {self.driver.page_source}")

            if attempt < max_attempts - 1:
                logger.debug("Refreshing page to retry finding 'Easy Apply' button.")
                self.driver.refresh()
                try:
                    self.wait.until(EC.presence_of_element_located((By.XPATH, '//button')))
                    logger.debug("Page refreshed and buttons reloaded.")
                except TimeoutException as te:
                    logger.warning("Timed out waiting for buttons to load after refresh.")
                    logger.warning(f"Página atual HTML: {self.driver.page_source}")

        # After max attempts, raise an exception if the button is not found
        logger.error("No clickable 'Easy Apply' button found after multiple attempts.")
        logger.debug(f"Página atual HTML: {self.driver.page_source}")
        raise Exception("No clickable 'Easy Apply' button found.")

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
            logger.debug(f"Página atual HTML: {self.driver.page_source}")
        except TimeoutException:
            logger.debug("No 'Job search safety reminder' modal detected.")
        except Exception as e:
            logger.warning(f"Unexpected error while handling safety reminder modal: {e}", exc_info=True)
            logger.debug(f"Página atual HTML: {self.driver.page_source}")

    def _find_buttons_by_xpath(self, xpath: str) -> List[WebElement]:
        """
        Finds multiple buttons based on the provided XPath.
        """
        logger.debug(f"Searching for buttons with XPath: {xpath}")
        return self.wait.until(lambda d: d.find_elements(By.XPATH, xpath))

    def _find_single_button(self, xpath: str) -> WebElement:
        """
        Finds a single button based on the provided XPath.
        """
        logger.debug(f"Searching for single button with XPath: {xpath}")
        return self.wait.until(EC.presence_of_element_located((By.XPATH, xpath)))

    def _is_element_clickable(self, element: WebElement) -> bool:
        """
        Checks if a given WebElement is clickable.
        """
        try:
            self.wait.until(EC.visibility_of(element))
            self.wait.until(EC.element_to_be_clickable(element))
            logger.debug("Element is visible and clickable.")
            return True
        except Exception as e:
            logger.debug(f"Element is not clickable: {e}")
            return False

    def _get_job_description(self) -> str:
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
                logger.debug("Clicked 'See more description' button to expand job description")
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
            logger.warning(f"Página atual HTML: {self.driver.page_source}")
            raise Exception("Job description element not found") from e
        except TimeoutException as te:
            logger.warning("Timed out waiting for the job description element.")
            logger.warning(f"Página atual HTML: {self.driver.page_source}")
            raise Exception("Timed out waiting for the job description element") from te
        except Exception as e:
            logger.warning(f"Unexpected error in _get_job_description: {e}", exc_info=True)
            logger.warning(f"Página atual HTML: {self.driver.page_source}")
            raise Exception("Error getting job description") from e


    def _get_job_recruiter(self):
        logger.debug("Getting job recruiter information")
        try:
            hiring_team_section = self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, '//h2[text()="Meet the hiring team"]')
                )
            )
            logger.debug("Hiring team section found")

            recruiter_elements = hiring_team_section.find_elements(
                By.XPATH, './/following::a[contains(@href, "linkedin.com/in/")]'
            )

            if recruiter_elements:
                recruiter_element = recruiter_elements[0]
                recruiter_link = recruiter_element.get_attribute("href")
                logger.debug(
                    f"Job recruiter link retrieved successfully: {recruiter_link}"
                )
                return recruiter_link
            else:
                logger.debug("No recruiter link found in the hiring team section")
                return ""
        except TimeoutException:
            logger.warning(
                "Hiring team section not found within the timeout period"
            )
            return ""
        except Exception as e:
            logger.warning(
                f"Failed to retrieve recruiter information: {e}", exc_info=True
            )
            return ""

    def _scroll_page(self) -> None:
        logger.debug("Scrolling the page")
        try:
            scrollable_element = self.driver.find_element(By.TAG_NAME, "html")
            utils.scroll_slow(self.driver, scrollable_element, step=300, reverse=False)
            utils.scroll_slow(
                self.driver, scrollable_element, step=300, reverse=True
            )
            logger.debug("Page scrolled successfully")
        except Exception as e:
            logger.warning(f"Failed to scroll the page: {e}", exc_info=True)

    def _fill_application_form(self, job: Job):
        logger.debug(f"Filling out application form for job: {job.title} at {job.company}")
        while True:
            self.fill_up(job)
            if self._next_or_submit():
                logger.debug("Application form submitted successfully")
                break

    def _next_or_submit(self):
        logger.debug("Clicking 'Next' or 'Submit' button")

        try:
            # Explicit wait until button is clickable
            next_button = self.wait.until(
                EC.element_to_be_clickable(
                    (By.CLASS_NAME, "artdeco-button--primary")
                )
            )

            button_text = next_button.text.lower()
            if "submit application" in button_text:
                logger.debug("Submit button found, submitting application")
                self._unfollow_company()
                self.wait.until(EC.element_to_be_clickable(next_button))
                # time.sleep(random.uniform(0.5, 1.5))

                # Attempt to click the submit button
                next_button.click()
                self.wait.until(EC.staleness_of(next_button))
                # time.sleep(random.uniform(0.5, 1.5))
                logger.debug("Application submitted")
                return True

            # For the "Next" button
            # time.sleep(random.uniform(0.5, 1.5))
            next_button.click()
            self.wait.until(EC.staleness_of(next_button))
            # time.sleep(random.uniform(0.5, 1.5))
            logger.debug("'Next' button clicked")
            self._check_for_errors()
            return False

        except ElementNotInteractableException:
            logger.error(
                "Element not interactable while attempting to click 'Next' or 'Submit' button",
                exc_info=True,
            )
            return False  # Return False if the button is not clickable

        except TimeoutException:
            logger.error(
                "Timed out waiting for the 'Next' or 'Submit' button to become clickable",
                exc_info=True,
            )
            return False

        except Exception as e:
            logger.error(
                f"Unexpected error when clicking 'Next' or 'Submit' button: {e}",
                exc_info=True,
            )
            return False

    def _unfollow_company(self) -> None:
        try:
            logger.debug(
                "Unfollowing company to avoid staying updated with their page"
            )
            follow_checkbox = self.wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//label[contains(.,'to stay up to date with their page.')]",
                    )
                )
            )
            follow_checkbox.click()
            logger.debug("Unfollowed company successfully")
        except TimeoutException:
            logger.warning(
                "Unfollow checkbox not found within the timeout period, possibly already unfollowed"
            )
        except Exception as e:
            logger.warning(
                f"Failed to unfollow company: {e}", exc_info=True
            )

    def _check_for_errors(self) -> None:
        logger.debug("Checking for form errors")
        try:
            error_elements = self.driver.find_elements(
                By.CLASS_NAME, "artdeco-inline-feedback--error"
            )
            if error_elements:
                error_texts = [e.text for e in error_elements]
                logger.error(
                    f"Form submission failed with errors: {error_texts}"
                )
                raise Exception(f"Failed answering or file upload. {error_texts}")
            else:
                logger.debug("No form errors detected")
        except Exception as e:
            logger.error(f"Error while checking for form errors: {e}", exc_info=True)
            raise

    def _discard_application(self) -> None:
        logger.debug("Discarding application")
        try:
            dismiss_button = self.wait.until(
                EC.element_to_be_clickable(
                    (By.CLASS_NAME, "artdeco-modal__dismiss")
                )
            )
            dismiss_button.click()
            logger.debug("Clicked dismiss button on application modal")
            self.wait.until(EC.staleness_of(dismiss_button))
            # time.sleep(random.uniform(0.5, 1.5))

            confirm_buttons = self.driver.find_elements(
                By.CLASS_NAME, "artdeco-modal__confirm-dialog-btn"
            )
            if confirm_buttons:
                self.wait.until(
                    EC.element_to_be_clickable(confirm_buttons[0])
                )
                confirm_buttons[0].click()
                logger.debug("Confirmed discarding application")
                self.wait.until(EC.staleness_of(confirm_buttons[0]))
                # time.sleep(random.uniform(0.5, 1.5))
            else:
                logger.warning("Confirm discard button not found")
        except TimeoutException:
            logger.warning("Discard modal elements not found within the timeout period")
        except Exception as e:
            logger.warning(
                f"Failed to discard application: {e}", exc_info=True
            )

    def fill_up(self, job: Job) -> None:
        logger.debug(
            f"Starting to fill up form sections for job: {job.title} at {job.company}"
        )

        try:
            # Wait for the easy apply content section to be present
            try:
                easy_apply_content = self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "jobs-easy-apply-content")))
                logger.debug("Easy apply content section found successfully.")
            except NoSuchElementException:
                logger.error("Easy apply content section not found")
                raise
            except TimeoutException as te:
                logger.exception("Easy apply content section not found within the timeout period")
                raise
            except Exception as e:
                logger.exception("Error while finding easy apply content section")
                raise

            # Find all form sections within the easy apply content
            pb4_elements = easy_apply_content.find_elements(By.CLASS_NAME, "pb4")
            logger.debug(f"Found {len(pb4_elements)} form sections to process.")

            # Process each form section
            for index, element in enumerate(pb4_elements):
                logger.debug(f"Processing form section {index + 1}/{len(pb4_elements)}")
                self._process_form_element(element, job)
            logger.debug("All form sections processed successfully.")

        except TimeoutException:
            logger.error("Easy apply content section not found within the timeout period",exc_info=True,)
            raise
        except Exception as e:
            logger.error(f"An error occurred while filling up the form: {e}", exc_info=True)
            raise

    def _process_form_element(self, element: WebElement, job: Job) -> None:
        logger.debug("Processing form element")
        if self._is_upload_field(element):
            self._handle_upload_fields(element, job)
        else:
            self._fill_additional_questions(job)

    def _handle_dropdown_fields(self, element: WebElement) -> None:
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
        for item in self.all_data:
            if (
                self._sanitize_text(question_text) in item["question"]
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

    def _is_upload_field(self, element: WebElement) -> bool:
        is_upload = bool(element.find_elements(By.XPATH, ".//input[@type='file']"))
        logger.debug(f"Element is upload field: {is_upload}")
        return is_upload

    def _handle_upload_fields(self, element: WebElement, job) -> None:
        logger.debug("Handling upload fields")
        try:
            show_more_button = self.wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//button[contains(@aria-label, 'Show more resumes')]",
                    )
                )
            )
            show_more_button.click()
            logger.debug("Clicked 'Show more resumes' button")
        except TimeoutException:
            logger.warning(
                "'Show more resumes' button not found within the timeout period, continuing with available upload fields"
            )

        file_upload_elements = self.driver.find_elements(
            By.XPATH, "//input[@type='file']"
        )
        logger.debug(
            f"Found {len(file_upload_elements)} file upload elements"
        )

        for file_element in file_upload_elements:
            parent = file_element.find_element(By.XPATH, "..")
            self.driver.execute_script(
                "arguments[0].classList.remove('hidden')", file_element
            )
            logger.debug("Made file upload element visible")

            output = self.gpt_answerer.resume_or_cover(parent.text.lower())
            if "resume" in output:
                logger.debug("Uploading resume")
                if (
                    self.resume_path is not None
                    and Path(self.resume_path).resolve().is_file()
                ):
                    try:
                        file_element.send_keys(
                            str(Path(self.resume_path).resolve())
                        )
                        logger.debug(
                            f"Resume uploaded from path: {Path(self.resume_path).resolve()}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to upload resume from path: {self.resume_path}",
                            exc_info=True,
                        )
                        raise
                else:
                    logger.warning(
                        "Resume path not found or invalid, generating new resume"
                    )
                    self._create_and_upload_resume(file_element, job)
            elif "cover" in output:
                logger.debug("Uploading cover letter")
                self._create_and_upload_cover_letter(file_element, job)
            else:
                logger.warning(
                    f"Unexpected output from resume_or_cover: {output}"
                )

        logger.debug("Finished handling upload fields")

    def _create_and_upload_resume(self, element, job):
        logger.debug("Starting the process of creating and uploading resume.")
        folder_path = "generated_cv"

        try:
            if not os.path.exists(folder_path):
                logger.debug(f"Creating directory at path: {folder_path}")
            os.makedirs(folder_path, exist_ok=True)
            logger.debug(f"Directory ensured at path: {folder_path}")
        except Exception as e:
            logger.exception(f"Failed to create directory: {folder_path}")
            raise

        while True:
            try:
                timestamp = int(time.time())
                file_path_pdf = os.path.join(folder_path, f"CV_{timestamp}.pdf")
                logger.debug(f"Generated file path for resume: {file_path_pdf}")

                logger.debug(
                    f"Generating resume for job: {job.title} at {job.company}"
                )
                resume_pdf_base64 = self.resume_generator_manager.pdf_base64(
                    job_description_text=job.description
                )
                with open(file_path_pdf, "xb") as f:
                    f.write(base64.b64decode(resume_pdf_base64))
                logger.debug(
                    f"Resume successfully generated and saved to: {file_path_pdf}"
                )

                break
            except HTTPStatusError as e:
                if e.response.status_code == 429:

                    retry_after = e.response.headers.get("retry-after")
                    retry_after_ms = e.response.headers.get("retry-after-ms")

                    if retry_after:
                        wait_time = int(retry_after)
                        logger.warning(
                            f"Rate limit exceeded, waiting {wait_time} seconds before retrying..."
                        )
                    elif retry_after_ms:
                        wait_time = int(retry_after_ms) / 1000.0
                        logger.warning(
                            f"Rate limit exceeded, waiting {wait_time} milliseconds before retrying..."
                        )
                    else:
                        wait_time = 20
                        logger.warning(
                            f"Rate limit exceeded, waiting {wait_time} seconds before retrying..."
                        )

                    time.sleep(wait_time)
                else:
                    logger.exception(
                        f"HTTP error occurred while generating resume: {e}"
                    )
                    raise

            except Exception as e:
                logger.exception("Failed to generate resume")
                if "RateLimitError" in str(e):
                    logger.warning("Rate limit error encountered, retrying after wait")
                    time.sleep(20)
                else:
                    raise

        file_size = os.path.getsize(file_path_pdf)
        max_file_size = 2 * 1024 * 1024  # 2 MB
        logger.debug(f"Resume file size: {file_size} bytes")
        if file_size > max_file_size:
            logger.error(
                f"Resume file size exceeds 2 MB: {file_size} bytes"
            )
            raise ValueError(
                "Resume file size exceeds the maximum limit of 2 MB."
            )

        allowed_extensions = {".pdf", ".doc", ".docx"}
        file_extension = os.path.splitext(file_path_pdf)[1].lower()
        logger.debug(f"Resume file extension: {file_extension}")
        if file_extension not in allowed_extensions:
            logger.error(
                f"Invalid resume file format: {file_extension}"
            )
            raise ValueError(
                "Resume file format is not allowed. Only PDF, DOC, and DOCX formats are supported."
            )

        try:
            logger.debug(f"Uploading resume from path: {file_path_pdf}")
            element.send_keys(os.path.abspath(file_path_pdf))
            job.pdf_path = os.path.abspath(file_path_pdf)
            try:
                self.wait.until(
                    EC.presence_of_element_located((By.XPATH, f"//a[@href='{job.pdf_path}']"))
                )
            except TimeoutException:
                logger.warning(
                    f"Uploaded resume link not found on the page: {job.pdf_path}"
                )
            time.sleep(2)
            logger.debug(
                f"Resume uploaded successfully from: {file_path_pdf}"
            )
        except Exception as e:
            logger.exception("Resume upload failed")
            raise Exception("Upload failed") from e

    def _create_and_upload_cover_letter(
        self, element: WebElement, job
    ) -> None:
        logger.debug("Starting the process of creating and uploading the cover letter.")

        cover_letter_text = self.gpt_answerer.answer_question_textual_wide_range(
            "Write a cover letter", job=job
        )

        folder_path = "generated_cv"

        try:
            if not os.path.exists(folder_path):
                logger.debug(f"Creating directory at path: {folder_path}")
            os.makedirs(folder_path, exist_ok=True)
            logger.debug(f"Directory ensured at path: {folder_path}")
        except Exception as e:
            logger.exception(f"Failed to create directory: {folder_path}")
            raise

        while True:
            try:
                timestamp = int(time.time())
                file_path_pdf = os.path.join(
                    folder_path, f"Cover_Letter_{timestamp}.pdf"
                )
                logger.debug(
                    f"Generated file path for the cover letter: {file_path_pdf}"
                )

                # Create the PDF canvas
                c = canvas.Canvas(file_path_pdf, pagesize=A4)
                page_width, page_height = A4

                # Define styles
                styles = getSampleStyleSheet()
                styleN = styles['Normal']
                styleN.fontName = 'Helvetica'
                styleN.fontSize = 12
                styleN.leading = 15  # Line spacing
                styleN.alignment = TA_JUSTIFY  # Justify the text

                # Create a Paragraph object with the cover letter text
                paragraph = Paragraph(cover_letter_text, styleN)

                # Define a Frame for the paragraph
                frame = Frame(
                    inch,  # Left margin
                    inch,  # Bottom margin
                    page_width - 2 * inch,  # Width of the frame
                    page_height - 2 * inch,  # Height of the frame
                    showBoundary=0  # Set to 1 to visualize the borders (useful for debugging)
                )

                # Add the paragraph to the frame
                frame.addFromList([paragraph], c)

                # Save the PDF
                c.save()
                logger.debug(
                    f"Cover letter generated successfully and saved at: {file_path_pdf}"
                )

                break
            except Exception as e:
                logger.warning("Failed to generate the cover letter")
                raise

        # Check the file size and extension, as before
        file_size = os.path.getsize(file_path_pdf)
        max_file_size = 2 * 1024 * 1024  # 2 MB
        logger.debug(f"File size of the cover letter: {file_size} bytes")
        if file_size > max_file_size:
            logger.error(
                f"The file size of the cover letter exceeds 2 MB: {file_size} bytes"
            )
            raise ValueError(
                "The file size of the cover letter exceeds the maximum limit of 2 MB."
            )

        allowed_extensions = {".pdf", ".doc", ".docx"}
        file_extension = os.path.splitext(file_path_pdf)[1].lower()
        logger.debug(f"File extension of the cover letter: {file_extension}")
        if file_extension not in allowed_extensions:
            logger.error(
                f"Invalid file format for the cover letter: {file_extension}"
            )
            raise ValueError(
                "The file format of the cover letter is not allowed. Only PDF, DOC, and DOCX formats are supported."
            )

        try:
            logger.debug(f"Uploading the cover letter from path: {file_path_pdf}")
            element.send_keys(os.path.abspath(file_path_pdf))
            job.cover_letter_path = os.path.abspath(file_path_pdf)
            try:
                self.wait.until(
                    EC.presence_of_element_located(
                        (By.XPATH, f"//a[@href='{job.cover_letter_path}']")
                    )
                )
            except TimeoutException:
                logger.warning(
                    f"Link to the submitted cover letter not found on the page: {job.cover_letter_path}"
                )
            time.sleep(2)
            logger.debug(
                f"Cover letter submitted successfully from: {file_path_pdf}"
            )
        except Exception as e:
            logger.warning("Failed to send the cover letter")
            raise Exception("Submission failure") from e


    def _fill_additional_questions(self, job: Job) -> None:
        logger.debug("Filling additional questions")
        try:
            form_sections = self.wait.until(
                EC.presence_of_all_elements_located(
                    (By.CLASS_NAME, "jobs-easy-apply-form-section__grouping")
                )
            )
            logger.debug(
                f"Found {len(form_sections)} additional form sections to process"
            )
            for section in form_sections:
                self._process_form_section(section, job)
        except TimeoutException:
            logger.warning(
                "Additional form sections not found within the timeout period",
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.warning(
                f"An error occurred while filling additional questions: {e}",
                exc_info=True,
            )
            raise

    def _process_form_section(self, section: WebElement, job: Job) -> None:
        logger.debug("Processing form section")
        if self._handle_terms_of_service(section):
            logger.debug("Handled terms of service")
            return
        if self._find_and_handle_radio_question(section, job):
            logger.debug("Handled radio question")
            return
        if self._find_and_handle_textbox_question(section, job):
            logger.debug("Handled textbox question")
            return
        if self._find_and_handle_date_question(section, job):
            logger.debug("Handled date question")
            return

        if self._find_and_handle_dropdown_question(section, job):
            logger.debug("Handled dropdown question")
            return
        logger.debug(
            "No recognizable question type handled in this section"
        )

    def _handle_terms_of_service(self, element: WebElement) -> bool:
        logger.debug("Handling terms of service checkbox")
        labels = element.find_elements(By.TAG_NAME, "label")
        if labels and any(
            term in labels[0].text.lower()
            for term in ["terms of service", "privacy policy", "terms of use"]
        ):
            try:
                self.wait.until(
                    EC.element_to_be_clickable(labels[0])
                ).click()
                logger.debug("Clicked terms of service checkbox")
                return True
            except Exception as e:
                logger.warning(
                    f"Failed to click terms of service checkbox: {e}",
                    exc_info=True,
                )
        return False

    def _find_and_handle_radio_question(self, section: WebElement, job: Job) -> bool:
        logger.debug("Searching for radio questions in the section.")
        try:
            question = section.find_element(
                By.CLASS_NAME, "jobs-easy-apply-form-element"
            )
            radios = question.find_elements(
                By.CLASS_NAME, "fb-text-selectable__option"
            )
            if radios:
                question_text = section.text.lower()
                options = [radio.text.lower() for radio in radios]

                existing_answer = None
                for item in self.all_data:
                    if (
                        self._sanitize_text(question_text) in item["question"]
                        and item["type"] == "radio"
                    ):
                        existing_answer = item["answer"]
                        break
                if existing_answer:
                    logger.debug(
                        f"Using existing radio answer: {existing_answer}"
                    )
                    self._select_radio(radios, existing_answer)
                    return True

                logger.debug(
                    f"No existing answer found, querying model for: {question_text}"
                )
                answer = self.gpt_answerer.answer_question_from_options(
                    question_text, options
                )
                logger.debug(f"Model provided radio answer: {answer}")
                self._save_questions_to_json(
                    {"type": "radio", "question": question_text, "answer": answer}
                )
                self._select_radio(radios, answer)
                logger.debug("Selected new radio answer from model")
                return True
            return False
        except Exception as e:
            logger.warning(
                f"Failed to handle radio question: {e}", exc_info=True
            )
            return False

    def _find_and_handle_textbox_question(self, section: WebElement, job: Job) -> bool:
        logger.debug("Searching for text fields in the section.")
        text_fields = (
            section.find_elements(By.TAG_NAME, "input")
            + section.find_elements(By.TAG_NAME, "textarea")
        )

        if text_fields:
            text_field = text_fields[0]
            label_elements = section.find_elements(By.TAG_NAME, "label")
            question_text = (
                label_elements[0].text.lower().strip()
                if label_elements
                else "unknown"
            )
            logger.debug(f"Found text field with label: {question_text}")

            is_numeric = self._is_numeric_field(text_field)
            logger.debug(
                f"Is the field numeric? {'Yes' if is_numeric else 'No'}"
            )

            question_type = "numeric" if is_numeric else "textbox"

            # Check if it's a cover letter field (case-insensitive)
            is_cover_letter = "cover letter" in question_text.lower()

            # Look for existing answer if it's not a cover letter field
            existing_answer = None
            if not is_cover_letter:
                for item in self.all_data:
                    if (
                        self._sanitize_text(item["question"])
                        == self._sanitize_text(question_text)
                        and item.get("type") == question_type
                    ):
                        existing_answer = item["answer"]
                        logger.debug(
                            f"Found existing answer: {existing_answer}"
                        )
                        break

            if existing_answer and not is_cover_letter:
                answer = existing_answer
                logger.debug(f"Using existing answer: {answer}")
            else:
                if is_numeric:
                    answer = self.gpt_answerer.answer_question_numeric(
                        question_text
                    )
                    logger.debug(f"Generated numeric answer: {answer}")
                else:
                    answer = self.gpt_answerer.answer_question_textual_wide_range(
                        question_text, job=job
                    )
                    logger.debug(f"Generated textual answer: {answer}")

            self._enter_text(text_field, answer)
            logger.debug("Entered answer into the textbox.")

            # Save non-cover letter answers
            if not is_cover_letter:
                self._save_questions_to_json(
                    {
                        "type": question_type,
                        "question": question_text,
                        "answer": answer,
                    }
                )
                logger.debug("Saved non-cover letter answer to JSON.")

            try:
                self.wait.until(EC.element_to_be_clickable(text_field)).send_keys(
                    Keys.ARROW_DOWN
                )
                self.wait.until(EC.element_to_be_clickable(text_field)).send_keys(
                    Keys.ENTER
                )
                logger.debug("Selected first option from the dropdown.")
            except Exception as e:
                logger.warning(
                    f"Failed to send keys to text field: {e}",
                    exc_info=True,
                )
            return True

        logger.debug("No text fields found in the section.")
        return False

    def _find_and_handle_date_question(self, section: WebElement, job: Job) -> bool:
        logger.debug("Searching for date fields in the section.")
        date_fields = section.find_elements(
            By.CLASS_NAME, "artdeco-datepicker__input "
        )
        if date_fields:
            date_field = date_fields[0]
            question_text = section.text.lower()
            answer_date = self.gpt_answerer.answer_question_date()
            answer_text = answer_date.strftime("%Y-%m-%d")

            existing_answer = None
            for item in self.all_data:
                if (
                    self._sanitize_text(question_text) in item["question"]
                    and item["type"] == "date"
                ):
                    existing_answer = item["answer"]
                    break
            if existing_answer:
                logger.debug(
                    f"Using existing date answer: {existing_answer}"
                )
                self._enter_text(date_field, existing_answer)
                return True

            logger.debug(
                f"No existing date answer found, using generated date: {answer_text}"
            )
            self._save_questions_to_json(
                {"type": "date", "question": question_text, "answer": answer_text}
            )
            self._enter_text(date_field, answer_text)
            logger.debug("Entered new date answer")
            return True
        logger.debug("No date fields found in the section.")
        return False

    def _find_and_handle_dropdown_question(self, section: WebElement, job: Job) -> bool:
        logger.debug("Searching for dropdown or combobox questions in the section.")
        try:
            question = section.find_element(
                By.CLASS_NAME, "jobs-easy-apply-form-element"
            )

            dropdowns = question.find_elements(By.TAG_NAME, "select")
            if not dropdowns:
                dropdowns = section.find_elements(
                    By.CSS_SELECTOR, "[data-test-text-entity-list-form-select]"
                )

            if dropdowns:
                dropdown = dropdowns[0]
                select = Select(dropdown)
                options = [option.text for option in select.options]

                logger.debug(f"Dropdown options found: {options}")

                label_elements = question.find_elements(By.TAG_NAME, "label")
                question_text = (
                    label_elements[0].text.lower().strip()
                    if label_elements
                    else "unknown"
                )
                logger.debug(
                    f"Processing dropdown or combobox question: {question_text}"
                )

                current_selection = select.first_selected_option.text
                logger.debug(f"Current selection: {current_selection}")

                existing_answer = None
                for item in self.all_data:
                    if (
                        self._sanitize_text(question_text) in item["question"]
                        and item["type"] == "dropdown"
                    ):
                        existing_answer = item["answer"]
                        break

                if existing_answer:
                    logger.debug(
                        f"Found existing answer for question '{question_text}': {existing_answer}"
                    )
                    if current_selection != existing_answer:
                        logger.debug(
                            f"Updating selection to: {existing_answer}"
                        )
                        self._select_dropdown_option(dropdown, existing_answer)
                    return True

                logger.debug(
                    f"No existing answer found, querying model for: {question_text}"
                )

                answer = self.gpt_answerer.answer_question_from_options(
                    question_text, options
                )
                logger.debug(f"Model provided dropdown answer: {answer}")
                self._save_questions_to_json(
                    {"type": "dropdown", "question": question_text, "answer": answer}
                )
                self._select_dropdown_option(dropdown, answer)
                logger.debug(f"Selected new dropdown answer: {answer}")
                return True

            else:

                logger.debug("No dropdown found. Logging elements for debugging.")
                elements = section.find_elements(By.XPATH, ".//*")
                logger.debug(
                    f"Elements found: {[element.tag_name for element in elements]}"
                )
                return False

        except Exception as e:
            logger.warning(
                f"Failed to handle dropdown or combobox question: {e}",
                exc_info=True,
            )
            return False

    def _is_numeric_field(self, field: WebElement) -> bool:
        logger.debug("Checking if field is numeric")
        field_type = field.get_attribute("type").lower()
        field_id = field.get_attribute("id").lower()
        is_numeric = (
            "numeric" in field_id
            or field_type == "number"
            or (
                "text" == field_type
                and "numeric" in field_id
            )
        )
        logger.debug(
            f"Field type: {field_type}, Field ID: {field_id}, Is numeric: {is_numeric}"
        )
        return is_numeric

    def _enter_text(self, element: WebElement, text: str) -> None:
        logger.debug(f"Entering text: {text}")
        try:
            self.wait.until(EC.element_to_be_clickable(element))
            element.clear()
            element.send_keys(text)
            logger.debug("Text entered successfully")
        except Exception as e:
            logger.warning(
                f"Failed to enter text: {text}", exc_info=True
            )
            raise

    def _select_radio(
        self, radios: List[WebElement], answer: str
    ) -> None:
        logger.debug(f"Selecting radio option: {answer}")
        for radio in radios:
            if answer.lower() in radio.text.lower():
                try:
                    label = radio.find_element(By.TAG_NAME, "label")
                    self.wait.until(EC.element_to_be_clickable(label)).click()
                    logger.debug(f"Radio option '{answer}' selected")
                    return
                except Exception as e:
                    logger.warning(
                        f"Failed to click radio option '{answer}': {e}",
                        exc_info=True,
                    )
        try:
            self.wait.until(
                EC.element_to_be_clickable(
                    radios[-1].find_element(By.TAG_NAME, "label")
                )
            ).click()
            logger.warning(
                f"Selected last radio option as fallback: {radios[-1].text}"
            )
        except Exception as e:
            logger.warning("Failed to select fallback radio option", exc_info=True)
            raise

    def _select_dropdown_option(
        self, element: WebElement, text: str
    ) -> None:
        logger.debug(f"Selecting dropdown option: {text}")
        try:
            select = Select(element)
            select.select_by_visible_text(text)
            logger.debug(
                f"Dropdown option '{text}' selected successfully"
            )
        except Exception as e:
            logger.warning(
                f"Failed to select dropdown option '{text}': {e}",
                exc_info=True,
            )
            raise

    def _save_questions_to_json(self, question_data: dict) -> None:
        output_file = "answers.json"
        question_data["question"] = self._sanitize_text(question_data["question"])
        logger.debug(f"Saving question data to JSON: {question_data}")
        try:
            try:
                with open(output_file, "r") as f:
                    try:
                        data = json.load(f)
                        if not isinstance(data, list):
                            logger.error(
                                "JSON file format is incorrect. Expected a list of questions."
                            )
                            raise ValueError(
                                "JSON file format is incorrect. Expected a list of questions."
                            )
                    except json.JSONDecodeError:
                        logger.exception("JSON decoding failed")
                        data = []
            except FileNotFoundError:
                logger.warning("JSON file not found, creating new file")
                data = []
            data.append(question_data)
            with open(output_file, "w") as f:
                json.dump(data, f, indent=4)
            logger.debug("Question data saved successfully to JSON")
        except Exception:
            logger.exception("Error saving questions data to JSON file")
            raise Exception("Error saving questions data to JSON file") from None

    def _sanitize_text(self, text: str) -> str:
        sanitized_text = (
            text.lower()
            .strip()
            .replace('"', "")
            .replace("\\", "")
            .replace("\n", " ")
            .replace("\r", "")
            .rstrip(",")
        )
        sanitized_text = re.sub(r"[\x00-\x1F\x7F]", "", sanitized_text)
        logger.debug(f"Sanitized text: {sanitized_text}")
        return sanitized_text