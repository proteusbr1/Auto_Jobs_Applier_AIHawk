import base64
import json
import os
import random
import re
import time
from typing import List, Optional, Any, Tuple
from datetime import datetime
import traceback

from httpx import HTTPStatusError
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
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
from app_config import MINIMUM_SCORE_JOB_APPLICATION, USER_RESUME_SUMMARY

import src.utils as utils
from loguru import logger


class AIHawkEasyApplier:
    def __init__(
        self,
        driver: Any,
        resume_dir: Optional[str],
        set_old_answers: List[Tuple[str, str, str]],
        gpt_answerer: Any,
        resume_generator_manager,
        wait_time: int = 10,  # Default wait time
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

    def apply_to_job(self, job: Any) -> None:
        """
        Starts the process of applying to a job.
        :param job: A job object with the job details.
        :return: None
        """
        logger.info(f"Initiating application process for job: {job.title} at {job.company}")
        try:
            self.job_apply(job)
            logger.info(
                f"Successfully applied to job: {job.title} at {job.company}"
            )
        except Exception as e:
            logger.error(
                f"Failed to apply to job: {job.title} at {job.company}", exc_info=True
            )
            raise e

    def save_job_score(self, job: Any):
        """
        Saves jobs that were not applied to avoid future GPT queries, including the score and timestamp.
        """
        logger.debug(
            f"Saving skipped job: {job.title} at {job.company} with score {job.score}"
        )
        file_path = Path("data_folder") / "output" / "job_score.json"

        # Get current date and time
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Data format to be saved
        job_data = {
            "search_term": job.position,
            "company": job.company,
            "job_title": job.title,
            "link": job.link,
            "score": job.score,  # Adds the score to the record
            "timestamp": current_time,  # Adds the timestamp
        }

        # Check if file exists, if not, create a new one
        if not file_path.exists():
            try:
                with open(file_path, "w") as f:
                    json.dump([job_data], f, indent=4)
                logger.debug(f"Created new job_score.json with job: {job.title}")
            except Exception as e:
                logger.error(f"Failed to create job_score.json: {e}", exc_info=True)
                raise
        else:
            # If it exists, load existing data and append the new job
            try:
                with open(file_path, "r+") as f:
                    try:
                        existing_data = json.load(f)
                        if not isinstance(existing_data, list):
                            logger.warning(
                                "job_score.json format is incorrect. Overwriting with a new list."
                            )
                            existing_data = []
                    except json.JSONDecodeError:
                        logger.warning(
                            "job_score.json is empty or corrupted. Initializing with an empty list."
                        )
                        existing_data = []

                    existing_data.append(job_data)
                    f.seek(0)
                    json.dump(existing_data, f, indent=4)
                    f.truncate()
                logger.debug(f"Appended job to job_score.json: {job.title}")
            except Exception as e:
                logger.error(
                    f"Failed to append job to job_score.json: {e}", exc_info=True
                )
                raise
        logger.debug(
            f"Job saved successfully: {job.title} with score {job.score}"
        )

    def get_existing_job_score(self, link: str) -> float:
        """
        Retrieves the existing score for a job based on its link from job_score.json.
        """
        file_path = Path("data_folder") / "output" / "job_score.json"

        if not file_path.exists():
            logger.error("job_score.json does not exist. Returning default score of 0.")
            return 0.1

        try:
            with open(file_path, "r") as f:
                scored_jobs = json.load(f)
                for scored_job in scored_jobs:
                    if scored_job.get("link") == link:
                        return scored_job.get("score", 0.0)
        except Exception as e:
            logger.error(f"Error reading job_score.json: {e}", exc_info=True)

        return 0.1

    def is_job_already_scored(self, job_title, company, link):
        """
        Checks if the job has already been scored (skipped previously) and is in the job_score.json file.
        """
        logger.debug(
            f"Checking if job is already scored: Title='{job_title}', Company='{company}'."
        )
        file_path = Path("data_folder") / "output" / "job_score.json"

        # Early exit if the file doesn't exist
        if not file_path.exists():
            logger.debug("job_score.json does not exist. Job has not been scored.")
            return False

        # Load the scored jobs from the file
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                scored_jobs = json.load(f)
        except json.JSONDecodeError:
            logger.warning("job_score.json is corrupted. Considering job as not scored.")
            return False
        except Exception as e:
            logger.error(f"Error reading job_score.json: {e}", exc_info=True)
            return False

        # Check if the current job's link matches any scored job
        for scored_job in scored_jobs:
            if scored_job.get("link") == link:
                logger.debug(
                    f"Job already scored: Title='{job_title}', Company='{company}'."
                )
                return True

        logger.debug(f"Job not scored: Title='{job_title}', Company='{company}'.")
        return False

    def job_apply(self, job: Any):
        logger.info(f"Starting job application for job: {job.title} at {job.company}, link: {job.link}")

        try:
            self.driver.get(job.link)
            logger.debug(f"Navigated to job link: {job.link}")
            # try:
            #     self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'jobs-easy-apply-content')))
            #     logger.debug("Job page loaded successfully.")
            # except TimeoutException as te:
            #     logger.exception("Timeout while waiting for the job page to load.")
            #     raise

            self.check_for_premium_redirect(job)
            logger.debug("Checked for premium redirect.")

            logger.debug("Retrieving job description")
            job.description = self._get_job_description()

            if job.score is None:
                logger.debug("Evaluating job score using GPT.")
                job.score = self.gpt_answerer.evaluate_job(
                    job, USER_RESUME_SUMMARY
                )

            logger.debug(f"Job score is: {job.score}")

            if job.score >= MINIMUM_SCORE_JOB_APPLICATION:
                logger.info(
                    f"Proceeding with the application. Score is {job.score}."
                )
                try:
                    easy_apply_button = self._find_easy_apply_button(job)
                except Exception as e:
                    logger.error(f"Failed to find 'Easy Apply' button: {e}", exc_info=True)
                    self.save_job_score(job)
                    return False

                if easy_apply_button:
                    logger.debug("Easy Apply button found. Attempting to click.")
                    ActionChains(self.driver).move_to_element(
                        easy_apply_button
                    ).click().perform()
                    logger.debug("'Easy Apply' button clicked successfully")
                    self._fill_application_form(job)
                    self.save_job_score(job)
                    logger.debug(
                        f"Job application process completed successfully for job: {job.title} at {job.company}"
                    )
                    return True
                else:
                    logger.warning(
                        f"'Easy Apply' button not found for job: {job.title} at {job.company}"
                    )
                    self.save_job_score(job)
                    return False
            else:
                logger.info(
                    f"Score is {job.score}. Skipping application."
                )
                self.save_job_score(job)
                return False

        except Exception as e:
            logger.error(f"Failed to apply for the job: {e}")
            logger.debug("Discarding application due to failure")
            logger.debug(traceback.format_exc())
            # self._discard_application()
            raise

    def _find_easy_apply_button(self, job: Any) -> Optional[WebElement]:
        logger.debug("Searching for 'Easy Apply' button")
        attempt = 0

        search_methods = [
            {
                "description": "find all 'Easy Apply' buttons using find_elements",
                "find_elements": True,
                "xpath": '//button[contains(@class, "jobs-apply-button") and contains(., "Easy Apply")]',
            },
            {
                "description": "'aria-label' containing 'Easy Apply to'",
                "xpath": '//button[contains(@aria-label, "Easy Apply to")]',
            },
            {
                "description": "button text search",
                "xpath": '//button[contains(text(), "Easy Apply") or contains(text(), "Apply now")]',
            },
        ]

        while attempt < 2:

            self.check_for_premium_redirect(job)
            self._scroll_page()

            for method in search_methods:
                try:
                    logger.debug(f"Attempting search using {method['description']}")

                    if method.get("find_elements"):

                        try:
                            elements = self.wait.until(
                                lambda d: d.find_elements(By.XPATH, method["xpath"])
                            )
                            buttons = elements
                        except Exception as e:
                            logger.warning(
                                f"Exception occurred while finding elements using {method['description']}: {e}",
                                exc_info=True,
                            )
                            buttons = []

                        if buttons:
                            for index, button in enumerate(buttons):
                                try:
                                    self.wait.until(
                                        EC.visibility_of(button)
                                    )
                                    self.wait.until(
                                        EC.element_to_be_clickable(button)
                                    )
                                    logger.debug(
                                        f"Found 'Easy Apply' button {index + 1}, verifying clickability"
                                    )
                                    return button
                                except Exception as e:
                                    logger.warning(
                                        f"Button {index + 1} found but not clickable: {e}",
                                        exc_info=True,
                                    )
                        else:
                            raise TimeoutException("No 'Easy Apply' buttons found")
                    else:

                        try:
                            button = self.wait.until(
                                EC.presence_of_element_located((By.XPATH, method["xpath"]))
                            )
                            self.wait.until(EC.visibility_of(button))
                            self.wait.until(EC.element_to_be_clickable(button))
                            logger.debug("Found 'Easy Apply' button, verifying clickability")
                            return button
                        except Exception as e:
                            logger.warning(
                                f"Exception occurred while locating button using {method['description']}: {e}",
                                exc_info=True,
                            )
                            continue

                except TimeoutException:
                    logger.warning(
                        f"Timeout during search using {method['description']}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to find 'Easy Apply' button using {method['description']} on attempt {attempt + 1}: {e}",
                        exc_info=True,
                    )

            self.check_for_premium_redirect(job)

            if attempt == 0:
                logger.debug("Refreshing page to retry finding 'Easy Apply' button")
                self.driver.refresh()
                try:
                    self.wait.until(
                        EC.presence_of_element_located((By.XPATH, '//button'))
                    )
                except TimeoutException:
                    logger.warning(
                        "Timed out waiting for buttons to load after refresh."
                    )
                # time.sleep(random.randint(3, 5))
            attempt += 1

        page_source = self.driver.page_source
        logger.error(
            f"No clickable 'Easy Apply' button found after 2 attempts. Page source length: {len(page_source)} characters."
        )
        raise Exception("No clickable 'Easy Apply' button found")

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
        except TimeoutException as te:
            logger.exception(
                f"Job description not found within the timeout period: {te}"
            )
            raise Exception("Job description not found")
        except Exception as e:
            logger.exception(f"Error getting Job description: {e}")
            raise Exception("Error getting Job description")

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
                logger.info(
                    f"Job recruiter link retrieved successfully: {recruiter_link}"
                )
                return recruiter_link
            else:
                logger.info("No recruiter link found in the hiring team section")
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

    def _fill_application_form(self, job):
        logger.debug(
            f"Filling out application form for job: {job.title} at {job.company}"
        )
        while True:
            self.fill_up(job)
            if self._next_or_submit():
                logger.info("Application form submitted successfully")
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
                logger.info("Application submitted")
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

    def fill_up(self, job) -> None:
        logger.debug(
            f"Starting to fill up form sections for job: {job.title} at {job.company}"
        )

        try:
            # Wait for the easy apply content section to be present
            try:
                easy_apply_content = self.wait.until(
                    EC.presence_of_element_located(
                        (By.CLASS_NAME, "jobs-easy-apply-content")
                    )
                )
                logger.debug("Easy apply content section found successfully.")
            except TimeoutException as te:
                logger.exception(
                    "Easy apply content section not found within the timeout period"
                )
                raise

            # Find all form sections within the easy apply content
            pb4_elements = easy_apply_content.find_elements(By.CLASS_NAME, "pb4")
            logger.debug(
                f"Found {len(pb4_elements)} form sections to process."
            )

            # Process each form section
            for index, element in enumerate(pb4_elements):
                logger.debug(
                    f"Processing form section {index + 1}/{len(pb4_elements)}"
                )
                self._process_form_element(element, job)

            logger.debug("All form sections processed successfully.")

        except TimeoutException:
            logger.error(
                "Easy apply content section not found within the timeout period",
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(
                f"An error occurred while filling up the form: {e}", exc_info=True
            )
            raise

    def _process_form_element(self, element: WebElement, job) -> None:
        logger.debug("Processing form element")
        if self._is_upload_field(element):
            self._handle_upload_fields(element, job)
        else:
            self._fill_additional_questions()

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
        logger.info("Handling upload fields")
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
            logger.info(
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
                logger.info("Uploading resume")
                if (
                    self.resume_path is not None
                    and Path(self.resume_path).resolve().is_file()
                ):
                    try:
                        file_element.send_keys(
                            str(Path(self.resume_path).resolve())
                        )
                        logger.info(
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
                logger.info("Uploading cover letter")
                self._create_and_upload_cover_letter(file_element, job)
            else:
                logger.warning(
                    f"Unexpected output from resume_or_cover: {output}"
                )

        logger.info("Finished handling upload fields")

    def _create_and_upload_resume(self, element, job):
        logger.info("Starting the process of creating and uploading resume.")
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

                logger.info(
                    f"Generating resume for job: {job.title} at {job.company}"
                )
                resume_pdf_base64 = self.resume_generator_manager.pdf_base64(
                    job_description_text=job.description
                )
                with open(file_path_pdf, "xb") as f:
                    f.write(base64.b64decode(resume_pdf_base64))
                logger.info(
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
            logger.info(f"Uploading resume from path: {file_path_pdf}")
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
            logger.info(
                f"Resume uploaded successfully from: {file_path_pdf}"
            )
        except Exception as e:
            logger.exception("Resume upload failed")
            raise Exception("Upload failed") from e

    def _create_and_upload_cover_letter(
        self, element: WebElement, job
    ) -> None:
        logger.info("Starting the process of creating and uploading cover letter.")

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
                    f"Generated file path for cover letter: {file_path_pdf}"
                )

                c = canvas.Canvas(file_path_pdf, pagesize=A4)
                page_width, page_height = A4
                text_object = c.beginText(50, page_height - 50)
                text_object.setFont("Helvetica", 12)

                max_width = page_width - 100
                bottom_margin = 50
                available_height = page_height - bottom_margin - 50

                def split_text_by_width(text, font, font_size, max_width):
                    wrapped_lines = []
                    for line in text.splitlines():

                        if utils.string_width(line, font, font_size) > max_width:
                            words = line.split()
                            new_line = ""
                            for word in words:
                                if utils.stringWidth(
                                    new_line + word + " ", font, font_size
                                ) <= max_width:
                                    new_line += word + " "
                                else:
                                    wrapped_lines.append(new_line.strip())
                                    new_line = word + " "
                            wrapped_lines.append(new_line.strip())
                        else:
                            wrapped_lines.append(line)
                    return wrapped_lines

                lines = split_text_by_width(
                    cover_letter_text, "Helvetica", 12, max_width
                )

                for line in lines:
                    text_height = text_object.getY()
                    if text_height > bottom_margin:
                        text_object.textLine(line)
                    else:

                        c.drawText(text_object)
                        c.showPage()
                        text_object = c.beginText(50, page_height - 50)
                        text_object.setFont("Helvetica", 12)
                        text_object.textLine(line)

                c.drawText(text_object)
                c.save()
                logger.info(
                    f"Cover letter successfully generated and saved to: {file_path_pdf}"
                )

                break
            except Exception as e:
                logger.exception("Failed to generate cover letter")
                raise

        file_size = os.path.getsize(file_path_pdf)
        max_file_size = 2 * 1024 * 1024  # 2 MB
        logger.debug(f"Cover letter file size: {file_size} bytes")
        if file_size > max_file_size:
            logger.error(
                f"Cover letter file size exceeds 2 MB: {file_size} bytes"
            )
            raise ValueError(
                "Cover letter file size exceeds the maximum limit of 2 MB."
            )

        allowed_extensions = {".pdf", ".doc", ".docx"}
        file_extension = os.path.splitext(file_path_pdf)[1].lower()
        logger.debug(f"Cover letter file extension: {file_extension}")
        if file_extension not in allowed_extensions:
            logger.error(
                f"Invalid cover letter file format: {file_extension}"
            )
            raise ValueError(
                "Cover letter file format is not allowed. Only PDF, DOC, and DOCX formats are supported."
            )

        try:
            logger.info(f"Uploading cover letter from path: {file_path_pdf}")
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
                    f"Uploaded cover letter link not found on the page: {job.cover_letter_path}"
                )
            time.sleep(2)
            logger.info(
                f"Cover letter uploaded successfully from: {file_path_pdf}"
            )
        except Exception as e:
            logger.exception("Cover letter upload failed")
            raise Exception("Upload failed") from e

    def _fill_additional_questions(self) -> None:
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
                self._process_form_section(section)
        except TimeoutException:
            logger.error(
                "Additional form sections not found within the timeout period",
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(
                f"An error occurred while filling additional questions: {e}",
                exc_info=True,
            )
            raise

    def _process_form_section(self, section: WebElement) -> None:
        logger.debug("Processing form section")
        if self._handle_terms_of_service(section):
            logger.debug("Handled terms of service")
            return
        if self._find_and_handle_radio_question(section):
            logger.debug("Handled radio question")
            return
        if self._find_and_handle_textbox_question(section):
            logger.debug("Handled textbox question")
            return
        if self._find_and_handle_date_question(section):
            logger.debug("Handled date question")
            return

        if self._find_and_handle_dropdown_question(section):
            logger.debug("Handled dropdown question")
            return
        logger.debug(
            "No recognizable question type handled in this section"
        )

    def _handle_terms_of_service(self, element: WebElement) -> bool:
        labels = element.find_elements(By.TAG_NAME, "label")
        if labels and any(
            term in labels[0].text.lower()
            for term in ["terms of service", "privacy policy", "terms of use"]
        ):
            try:
                self.wait.until(
                    EC.element_to_be_clickable(labels[0])
                ).click()
                logger.info("Clicked terms of service checkbox")
                return True
            except Exception as e:
                logger.error(
                    f"Failed to click terms of service checkbox: {e}",
                    exc_info=True,
                )
        return False

    def _find_and_handle_radio_question(self, section: WebElement) -> bool:
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
                logger.info("Selected new radio answer from model")
                return True
            return False
        except Exception as e:
            logger.warning(
                f"Failed to handle radio question: {e}", exc_info=True
            )
            return False

    def _find_and_handle_textbox_question(self, section: WebElement) -> bool:
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
                        question_text
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

    def _find_and_handle_date_question(self, section: WebElement) -> bool:
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
            logger.info("Entered new date answer")
            return True
        logger.debug("No date fields found in the section.")
        return False

    def _find_and_handle_dropdown_question(self, section: WebElement) -> bool:
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
                logger.info(f"Selected new dropdown answer: {answer}")
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
            logger.error(
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
            logger.error("Failed to select fallback radio option", exc_info=True)
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
            logger.error(
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