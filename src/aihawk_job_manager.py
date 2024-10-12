import json
import os
import random
from itertools import product
from pathlib import Path

from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException 
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import src.utils as utils
from app_config import MINIMUM_WAIT_TIME, MINIMUM_SCORE_JOB_APPLICATION, USER_RESUME_SUMMARY, USE_JOB_SCORE
from src.job import Job
from src.aihawk_easy_applier import AIHawkEasyApplier
from loguru import logger


class EnvironmentKeys:
    def __init__(self):
        logger.debug("Initializing EnvironmentKeys")
        self.skip_apply = self._read_env_key_bool("SKIP_APPLY")
        self.disable_description_filter = self._read_env_key_bool("DISABLE_DESCRIPTION_FILTER")
        logger.debug(f"EnvironmentKeys initialized: skip_apply={self.skip_apply}, disable_description_filter={self.disable_description_filter}")

    @staticmethod
    def _read_env_key(key: str) -> str:
        value = os.getenv(key, "")
        logger.debug(f"Read environment key {key}: {value}")
        return value

    @staticmethod
    def _read_env_key_bool(key: str) -> bool:
        value = os.getenv(key) == "True"
        logger.debug(f"Read environment key {key} as bool: {value}")
        return value


class AIHawkJobManager:
    def __init__(self, driver, wait_time: int = 10):
        logger.debug("Initializing AIHawkJobManager")
        self.driver = driver
        self.wait = WebDriverWait(self.driver, wait_time)
        self.set_old_answers = set()
        self.easy_applier_component = None
        self.seen_jobs = []
        self.title_blacklist_set = set()
        self.company_blacklist_set = set()
        self.output_files_cache = {}
        self.applied_companies_cache = set()
        logger.debug("AIHawkJobManager initialized successfully")

    def set_parameters(self, parameters):
        logger.debug("Setting parameters for AIHawkJobManager")
        self.company_blacklist = parameters.get("company_blacklist", [])
        self.title_blacklist = parameters.get("title_blacklist", [])
        self.title_blacklist_set = set(word.lower().strip() for word in self.title_blacklist)
        self.company_blacklist_set = set(word.lower().strip() for word in self.company_blacklist)
        self.positions = parameters.get("positions", [])
        self.locations = parameters.get("locations", [])
        self.apply_once_at_company = parameters.get("apply_once_at_company", False)
        self.base_search_url = self.get_base_search_url(parameters)
        self.seen_jobs = []

        job_applicants_threshold = parameters.get("job_applicants_threshold", {})
        self.min_applicants = job_applicants_threshold.get("min_applicants", 0)
        self.max_applicants = job_applicants_threshold.get("max_applicants", float("inf"))

        resume_path = parameters.get("uploads", {}).get("resume", None)
        self.resume_path = Path(resume_path) if resume_path and Path(resume_path).exists() else None
        self.output_file_directory = Path(parameters["outputFileDirectory"])
        self.env_config = EnvironmentKeys()
        logger.debug("Parameters set successfully")
    def set_gpt_answerer(self, gpt_answerer):
        logger.debug("Setting GPT answerer")
        self.gpt_answerer = gpt_answerer

    def set_resume_generator_manager(self, resume_generator_manager):
        logger.debug("Setting resume generator manager")
        self.resume_generator_manager = resume_generator_manager

    def start_applying(self):
        logger.debug("Starting job application process")
        self.easy_applier_component = AIHawkEasyApplier(
            self.driver,
            self.resume_path,
            self.set_old_answers,
            self.gpt_answerer,
            self.resume_generator_manager
        )
        searches = list(product(self.positions, self.locations))
        random.shuffle(searches)
        page_sleep = 0

        for position, location in searches:
            location_url = "&location=" + location
            job_page_number = -1
            logger.debug(f"Starting the search for '{position}' in '{location}'.")

            try:
                while True:
                    page_sleep += 1
                    job_page_number += 1
                    logger.info(f"Navigating to job page {job_page_number} for position '{position}' in '{location}'.")
                    self.next_job_page(position, location_url, job_page_number)
                    logger.debug("Initiating the application process for this page.")

                    try:
                        jobs = self.get_jobs_from_page()
                        if not jobs:
                            logger.debug("No more jobs found on this page. Exiting loop.")
                            break
                    except Exception as e:
                        logger.error("Failed to retrieve jobs.", exc_info=True)
                        break

                    try:
                        self.apply_jobs(position)
                    except Exception as e:
                        logger.error(f"Error during job application: {e}", exc_info=True)
                        continue

                    logger.debug("Completed applying to jobs on this page.")

            except Exception as e:
                logger.error("Unexpected error during job search.", exc_info=True)
                continue

    def get_jobs_from_page(self):
        logger.debug("Starting get_jobs_from_page.")
        try:
            no_results_locator = (By.CLASS_NAME, 'jobs-search-no-results-banner')
            job_locator = (By.CSS_SELECTOR, 'ul.scaffold-layout__list-container > li.jobs-search-results__list-item[data-occludable-job-id]')

            logger.debug(f"Waiting for either {no_results_locator} or {job_locator}.")

            try:
                self.wait.until(
                    EC.any_of(
                        EC.presence_of_element_located(no_results_locator),
                        EC.presence_of_element_located(job_locator)
                    )
                )
                logger.debug("Elements condition met.")
            except TimeoutException:
                logger.warning("Timed out waiting for the 'no results' banner or the job elements.")
                return []

            # Verificar se o banner de "sem resultados" está presente
            no_results_elements = self.driver.find_elements(*no_results_locator)
            if no_results_elements:
                no_results_banner = no_results_elements[0]
                banner_text = no_results_banner.text.lower()
                logger.debug(f"No results banner text: '{banner_text}'.")
                if 'no matching jobs found' in banner_text or "unfortunately, things aren't" in banner_text:
                    logger.debug("No matching jobs found on this search.")
                    return []

            # Caso contrário, assumir que os resultados de empregos estão presentes
            try:
                job_list_container = self.wait.until(
                    EC.presence_of_element_located((By.CLASS_NAME, 'jobs-search-results-list'))
                )
                logger.debug("Job list container found.")

                # Scroll otimizado para carregar todos os elementos de trabalho
                logger.debug("Initiating optimized scroll to load all job elements.")
                utils.scroll_slow(self.driver, job_list_container, step=500, reverse=False, max_attempts=5)
                # utils.scroll_slow(self.driver, job_list_container, step=500, reverse=True, max_attempts=5)
                logger.debug("Scrolling completed.")

                job_list_elements = job_list_container.find_elements(By.CSS_SELECTOR, 'li.jobs-search-results__list-item[data-occludable-job-id]')
                logger.debug(f"Found {len(job_list_elements)} job elements on the page.")

                if not job_list_elements:
                    logger.error("No job elements found on the page, skipping.")
                    return []

                return job_list_elements

            except TimeoutException:
                logger.warning("Timed out waiting for the job list container to load.")
                return []
            except NoSuchElementException:
                logger.error("Job list container element not found on the page.")
                return []
            except StaleElementReferenceException:
                logger.error("StaleElementReferenceException encountered. Attempting to recapture job elements.")
                try:
                    job_list_container = self.driver.find_element(By.CSS_SELECTOR, 'ul.scaffold-layout__list-container')
                    job_list_elements = job_list_container.find_elements(By.CSS_SELECTOR, 'li.jobs-search-results__list-item[data-occludable-job-id]')
                    logger.debug(f"Recaptured {len(job_list_elements)} job elements after StaleElementReferenceException.")
                    return job_list_elements
                except Exception as e:
                    logger.error(f"Failed to recapture job elements after StaleElementReferenceException: {e}", exc_info=True)
                    return []
            except Exception as e:
                logger.error(f"Unexpected error while extracting job elements: {e}", exc_info=True)
                return []
        except TimeoutException:
            logger.warning("Timed out waiting for either 'no results' banner or job results list to load.")
            return []
        except Exception as e:
            logger.error(f"Error while fetching job elements. {e}", exc_info=True)
            return []

    def apply_jobs(self, position):
        try:
            job_list_container = self.wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, 'scaffold-layout__list-container'))
            )
            job_list_elements = job_list_container.find_elements(By.CLASS_NAME, 'jobs-search-results__list-item')
        except (TimeoutException, NoSuchElementException):
            logger.warning("Timed out waiting for job list container.")
            return

        if not job_list_elements:
            logger.warning("No job list elements found on page, skipping.")
            return

        job_list = [
            Job(*self.extract_job_information_from_tile(job_element), position=position)
            for job_element in job_list_elements
        ]

        for job in job_list:
            logger.debug(f"Evaluating job: '{job.title}' at '{job.company}'")

            # Check if the job must be skipped
            if self.must_be_skipped(job):
                logger.debug(f"Skipping job blacklisted: {job.link}")
                continue 
            
            # Check if the job has already been scored
            if USE_JOB_SCORE:
                if self.is_already_scored(job):
                    logger.debug(f"Job already scored: '{job.title}' at '{job.company}'.")
                    job.score = self.get_existing_score(job)
                
                if job.score is not None and job.score < MINIMUM_SCORE_JOB_APPLICATION:
                    logger.debug(f"Skipping by low score: {job.score}")
                    continue

            try:
                if self.easy_applier_component.job_apply(job):
                    utils.write_to_file(job, "success")
                    logger.info(f"Applied: {job.link}")

            except Exception as e:
                logger.error(
                        f"Failed to apply for job: Title='{job.title}', Company='{job.company}', "
                        f"Location='{job.location}', Link='{job.link}', Job State='{job.state}', Apply Method='{job.apply_method}', "
                        f"Error: {e}"
                    )
                utils.write_to_file(job, "failed")

            # Add job link to seen jobs set
            self.seen_jobs.append(job.link)


    def get_existing_score(self, job):
        """
        Retrieves the existing score for the job from the job_score.json file.
        """
        file_path = self.output_file_directory / 'job_score.json'
        link = job.link
        
        if not file_path.exists():
            return 0  # Return a default low score if file does not exist

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                scored_jobs = json.load(f)
                for scored_job in scored_jobs:
                    if scored_job.get('link') == link:
                        return scored_job.get('score', 0)  # Return existing score or 0 if not found
        except json.JSONDecodeError:
            logger.warning("job_score.json is corrupted. Returning score as 0.")
            return 0
        except Exception as e:
            logger.error(f"Error reading job_score.json: {e}", exc_info=True)
            return 0

    def get_base_search_url(self, parameters):
        logger.debug("Constructing base search URL.")
        url_parts = []
        if parameters.get('remote', False):
            url_parts.append("f_CF=f_WRA")
        experience_levels = [
            str(i + 1) for i, (level, v) in enumerate(parameters.get('experience_level', {}).items()) if v
        ]
        if experience_levels:
            url_parts.append(f"f_E={','.join(experience_levels)}")
        url_parts.append(f"distance={parameters.get('distance', 0)}")
        job_types = [key[0].upper() for key, value in parameters.get('jobTypes', {}).items() if value]
        if job_types:
            url_parts.append(f"f_JT={','.join(job_types)}")
        date_mapping = {
            "all time": "",
            "month": "&f_TPR=r2592000",
            "week": "&f_TPR=r604800",
            "24 hours": "&f_TPR=r86400"
        }
        date_param = next((v for k, v in date_mapping.items() if parameters.get('date', {}).get(k)), "")
        url_parts.append("f_LF=f_AL")  # Easy Apply
        base_url = "&".join(url_parts)
        full_url = f"?{base_url}{date_param}"
        logger.debug(f"Base search URL constructed: {full_url}")
        return full_url

    def next_job_page(self, position, location, job_page):
        logger.debug(f"Navigating to next job page: Position='{position}', Location='{location}', Page={job_page}.")
        self.driver.get(
            f"https://www.linkedin.com/jobs/search/{self.base_search_url}&keywords={position}{location}&start={job_page * 25}"
        )

    def extract_job_information_from_tile(self, job_tile):
        """
        Extracts job information from a job tile element.

        Args:
            job_tile (WebElement): The Selenium WebElement representing the job tile.

        Returns:
            Tuple[str, str, str, str, str, str]: A tuple containing job_title, company, job_location, link, apply_method, job_state.
        """
        logger.debug("Starting extraction of job information from tile.")

        # Initialize variables
        job_title = self._extract_job_title(job_tile)
        if job_tile:
            company = self._extract_company(job_tile)
            link = self._extract_link(job_tile)
            job_location = self._extract_job_location(job_tile)
            apply_method = self._extract_apply_method(job_tile)
            job_state = self._extract_job_state(job_tile)
        

        logger.debug(
            f"Completed extraction: Title='{job_title}', Company='{company}', "
            f"Location='{job_location}', Link='{link}', Job State='{job_state}', Apply Method='{apply_method}'"
        )

        return job_title, company, job_location, link, apply_method, job_state

    def _extract_job_title(self, job_tile):
        """
        Extracts the job title from the job tile.

        Args:
            job_tile (WebElement): The Selenium WebElement representing the job tile.

        Returns:
            str: The job title.
        """
        logger.debug("Extracting job title.")
        job_title = ""
        try:
            job_title_element = WebDriverWait(job_tile, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, ".//a[contains(@class, 'job-card-list__title')]")
            )
        )
            job_title = job_title_element.text.strip()
            logger.debug(f"Extracted Job Title: '{job_title}'")
        except NoSuchElementException:
            logger.error("Job title element not found.")
            logger.debug(f"HTML do job_tile: {job_tile.get_attribute('outerHTML')}")
        except TimeoutException:
            logger.error("Timed out waiting for the job title element.")
            logger.debug(f"HTML do job_tile: {job_tile.get_attribute('outerHTML')}")
        except Exception as e:
            logger.error(f"Unexpected error in _extract_job_title: {e}", exc_info=True)
            logger.debug(f"HTML do job_tile: {job_tile.get_attribute('outerHTML')}")
        return job_title


    def _extract_company(self, job_tile):
        """
        Extracts the company from the job tile.

        Args:
            job_tile (WebElement): The Selenium WebElement representing the job tile.

        Returns:
            str: The company name.
        """
        logger.debug("Extracting company.")
        company = ""
        try:
            company_element = WebDriverWait(job_tile, 2).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'job-card-container__primary-description')))
            company = company_element.text.strip()
            logger.debug(f"Extracted Company: '{company}'")
        except NoSuchElementException:
            logger.error("Element not found.")
            logger.debug(f"HTML do job_tile: {job_tile.get_attribute('outerHTML')}")
        except TimeoutException:
            logger.error("Timed out.")
            logger.debug(f"HTML do job_tile: {job_tile.get_attribute('outerHTML')}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            logger.debug(f"HTML do job_tile: {job_tile.get_attribute('outerHTML')}")
        return company

    def _extract_link(self, job_tile):
        """
        Extracts the job link from the job tile.

        Args:
            job_tile (WebElement): The Selenium WebElement representing the job tile.

        Returns:
            str: The job link.
        """
        logger.debug("Extracting job link.")
        link = ""
        try:
            job_title_element = WebDriverWait(job_tile, 2).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'job-card-list__title')))
            link = job_title_element.get_attribute('href').split('?')[0]
            logger.debug(f"Extracted Link: '{link}'")
        except NoSuchElementException:
            logger.error("Element not found.")
            logger.debug(f"HTML do job_tile: {job_tile.get_attribute('outerHTML')}")
        except TimeoutException:
            logger.error("Timed out.")
            logger.debug(f"HTML do job_tile: {job_tile.get_attribute('outerHTML')}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            logger.debug(f"HTML do job_tile: {job_tile.get_attribute('outerHTML')}")
        return link

    def _extract_job_location(self, job_tile):
        """
        Extracts the job location from the job tile.

        Args:
            job_tile (WebElement): The Selenium WebElement representing the job tile.

        Returns:
            str: The job location.
        """
        logger.debug("Extracting job location.")
        job_location = ""
        try:
            job_location_element = WebDriverWait(job_tile, 2).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'job-card-container__metadata-item'))
            )
            job_location = job_location_element.text.strip()
            logger.debug(f"Extracted Job Location: '{job_location}'")
        except NoSuchElementException:
            logger.error("Element not found.")
            logger.debug(f"HTML do job_tile: {job_tile.get_attribute('outerHTML')}")
        except TimeoutException:
            logger.error("Timed out.")
            logger.debug(f"HTML do job_tile: {job_tile.get_attribute('outerHTML')}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            logger.debug(f"HTML do job_tile: {job_tile.get_attribute('outerHTML')}")
        return job_location

    def _extract_apply_method(self, job_tile):
        """
        Extracts the apply method from the job_tile using the CSS class 'job-card-container__apply-method'.
        This is done only after ensuring that the <ul> element with the class 'job-card-container__footer-wrapper' is present.

        Args:
            job_tile (WebElement): The Selenium WebElement representing the job_tile.

        Returns:
            str: The apply method or None if it is not 'Easy Apply' or if the element is not found.
        """
        logger.debug("Starting apply method extraction.")
        apply_method = None
        try:
            # Wait for the footer <ul> element to be present
            WebDriverWait(job_tile, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'ul.job-card-container__footer-wrapper'))
            )
            logger.debug("Footer <ul> element found.")

            # Attempt to extract the apply method after the <ul> is present
            apply_method_element = job_tile.find_element(By.CLASS_NAME, 'job-card-container__apply-method')
            apply_method_text = apply_method_element.text.strip()
            logger.debug(f"Extracted apply method: '{apply_method_text}'")

            if apply_method_text.lower() == 'easy apply':
                apply_method = apply_method_text

        except TimeoutException:
            logger.debug("Timeout while waiting for the footer <ul> element.")
            logger.debug(f"HTML of job_tile: {job_tile.get_attribute('outerHTML')}")
        except NoSuchElementException:
            logger.debug("Element 'job-card-container__apply-method' not found.")
            # logger.debug(f"HTML of job_tile: {job_tile.get_attribute('outerHTML')}")
        except Exception as e:
            logger.debug(f"Unexpected error while extracting apply method: {e}", exc_info=True)
            logger.debug(f"HTML of job_tile: {job_tile.get_attribute('outerHTML')}")

        return apply_method


    def _extract_job_state(self, job_tile):
        """
        Extracts the job state from the job_tile using the CSS class 'job-card-container__footer-job-state'.
        This is done only after ensuring that the <ul> element with the class 'job-card-container__footer-wrapper' is present.

        Args:
            job_tile (WebElement): The Selenium WebElement representing the job_tile.

        Returns:
            str: The job state or None if the element is not found.
        """
        logger.debug("Starting job state extraction.")
        job_state = None
        try:
            # Wait for the footer <ul> element to be present
            WebDriverWait(job_tile, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'ul.job-card-container__footer-wrapper'))
            )
            logger.debug("Footer <ul> element found.")

            # Attempt to extract the job state after the <ul> is present
            job_state_element = job_tile.find_element(By.CLASS_NAME, 'job-card-container__footer-job-state')
            job_state_text = job_state_element.text.strip()
            logger.debug(f"Extracted job state: '{job_state_text}'")

            job_state = job_state_text

        except TimeoutException:
            logger.debug("Timeout while waiting for the footer <ul> element.")
            logger.debug(f"HTML of job_tile: {job_tile.get_attribute('outerHTML')}")
        except NoSuchElementException:
            logger.debug("Element 'job-card-container__footer-job-state' not found.")
            # logger.debug(f"HTML of job_tile: {job_tile.get_attribute('outerHTML')}")
        except Exception as e:
            logger.debug(f"Unexpected error while extracting job state: {e}", exc_info=True)
            logger.debug(f"HTML of job_tile: {job_tile.get_attribute('outerHTML')}")

        return job_state



    def must_be_skipped(self, job: Job) -> bool:
        """
        Determines if a given job should be skipped based on various criteria, including blacklist checks,
        job state, and apply method.

        Args:
            job (Job): The job object to evaluate.

        Returns:
            bool: True if the job should be skipped, False otherwise.
        """
        logger.debug("Checking if job should be skipped.")

        # Extract job information
        job_title = job.title
        company = job.company
        link = job.link

        # Check if job state is Applied, Continue, or Apply
        if self._is_job_state_invalid(job):
            logger.debug(f"Skipping by state: {job.state}")
            return True

        # Check if apply method is not 'Easy Apply'
        if self._is_apply_method_not_easy_apply(job):
            logger.debug(f"Skipping by apply method: {job.apply_method}")
            return True

        # Check Title Blacklist
        if self._is_title_blacklisted(job_title):
            logger.debug(f"Skipping by title blacklist: {job_title}")
            return True

        # Check Company Blacklist
        if self._is_company_blacklisted(company):
            logger.debug(f"Skipping by company blacklist: {company}")
            return True

        # Check if the link has already been seen
        if self._is_link_seen(link):
            logger.debug(f"Skipping by seen link: {link}")
            return True

        # Check if the job has already been applied to the company
        if self._is_already_applied_to_company(company):
            logger.debug(f"Skipping by company application policy: {company}")
            return True

        logger.debug("Job does not meet any skip conditions.")
        return False

    def _is_job_state_invalid(self, job: Job) -> bool:
        """
        Checks if the job state is not in the not valid states.

        Args:
            job (Job): The job object to evaluate.

        Returns:
            bool: True if job state is invalid, False otherwise.
        """
        return job.state in {"Continue", "Applied", "Apply"}

    def _is_apply_method_not_easy_apply(self, job: Job) -> bool:
        """
        Checks if the apply method is not 'Easy Apply'.

        Args:
            job (Job): The job object to evaluate.

        Returns:
            bool: True if apply method is not 'Easy Apply', False otherwise.
        """
        return job.apply_method != "Easy Apply"


    def _is_title_blacklisted(self, title: str) -> bool:
        """
        Checks if the job title contains any blacklisted words.

        Args:
            title (str): The job title to evaluate.

        Returns:
            bool: True if any blacklisted word is found in the title, False otherwise.
        """
        title_lower = title.lower()
        title_words = set(title_lower.split())
        intersection = title_words.intersection(self.title_blacklist_set)
        is_blacklisted = bool(intersection)

        if is_blacklisted:
            logger.debug(f"Blacklisted words found in title: {intersection}")

        return is_blacklisted

    def _is_company_blacklisted(self, company: str) -> bool:
        """
        Checks if the company name is in the blacklist.

        Args:
            company (str): The company name to evaluate.

        Returns:
            bool: True if the company is blacklisted, False otherwise.
        """
        company_cleaned = company.strip().lower()
        is_blacklisted = company_cleaned in self.company_blacklist_set

        if is_blacklisted:
            logger.debug(f"Company '{company_cleaned}' is in the blacklist.")

        return is_blacklisted

    def _is_link_seen(self, link: str) -> bool:
        """
        Checks if the job link has already been seen/applied to.

        Args:
            link (str): The job link to evaluate.

        Returns:
            bool: True if the link has been seen, False otherwise.
        """
        is_seen = link in self.seen_jobs

        if is_seen:
            logger.debug(f"Job link '{link}' has already been processed.")

        return is_seen

    def _is_already_applied_to_company(self, company: str) -> bool:
        """
        Determines if an application has already been submitted to the company's jobs,
        based on a one-application-per-company policy.

        Args:
            company (str): The company name to evaluate.

        Returns:
            bool: True if already applied to the company, False otherwise.
        """
        logger.debug("Checking if job has already been applied at the company.")
        company = company.strip().lower()

        if not self.apply_once_at_company:
            logger.debug("apply_once_at_company is disabled. Skipping check.")
            return False

        # Check cache first
        if company in self.applied_companies_cache:
            logger.debug(
                f"Company '{company}' is already in the applied companies cache. Skipping."
            )
            return True

        output_files = ["success.json"]
        for file_name in output_files:
            file_path = self.output_file_directory / file_name
            if not file_path.exists():
                logger.debug(f"Output file '{file_path}' does not exist. Skipping.")
                continue

            try:
                if file_path in self.output_files_cache:
                    existing_data = self.output_files_cache[file_path]
                else:
                    with open(file_path, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                        self.output_files_cache[file_path] = existing_data

                if not isinstance(existing_data, list):
                    logger.warning(f"Unexpected data format in '{file_path}'. Expected a list.")
                    continue

                for applied_job in existing_data:
                    if not isinstance(applied_job, dict):
                        logger.warning(f"Invalid job entry format in '{file_path}': {applied_job}. Skipping entry.")
                        continue
                    applied_company = applied_job.get("company", "").strip().lower()
                    if not applied_company:
                        logger.warning(f"Missing 'company' key in job entry: {applied_job}. Skipping entry.")
                        continue
                    if applied_company == company:
                        logger.debug(
                            f"Already applied at '{company}' (once per company policy). Skipping."
                        )
                        self.applied_companies_cache.add(company)
                        return True
            except json.JSONDecodeError:
                logger.error(f"JSON decode error in file: {file_path}. Skipping file.")
                continue
            except Exception as e:
                logger.error(f"Error reading file '{file_path}': {e}", exc_info=True)
                continue

        logger.debug(f"No previous applications found for company '{company}'.")
        return False
    
    def is_already_scored(self, job):
        """
        Checks if the job has already been scored (skipped previously) and is in the job_score.json file.
        """
        logger.debug(f"Checking if job is already scored.")
        job_title = job.title 
        company = job.company
        link = job.link
        file_path = self.output_file_directory / 'job_score.json'

        # Early exit if the file doesn't exist
        if not file_path.exists():
            logger.debug("job_score.json does not exist. Job has not been scored.")
            return False

        # Load the scored jobs from the file
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                scored_jobs = json.load(f)
        except json.JSONDecodeError:
            logger.warning("job_score.json is corrupted. Considering job as not scored.")
            return False
        except Exception as e:
            logger.error(f"Error reading job_score.json: {e}", exc_info=True)
            return False

        # Check if the current job's link matches any scored job
        for scored_job in scored_jobs:
            if scored_job.get('link') == link:
                logger.debug(f"Job already scored: Title='{job_title}', Company='{company}'.")
                return True

        logger.debug(f"Job not scored: Title='{job_title}', Company='{company}'.")
        return False