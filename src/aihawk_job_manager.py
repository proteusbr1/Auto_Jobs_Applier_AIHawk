# aihawk_job_manager.py
import json
import os
import random
from itertools import product
from pathlib import Path
import time

from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import src.utils as utils
from app_config import USE_JOB_SCORE
from src.job import Job, JobCache
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
        logger.debug("AIHawkJobManager initialized successfully")

    def set_parameters(self, parameters, resume_manager):
        logger.debug("Setting parameters for AIHawkJobManager")
        self.company_blacklist = parameters.get("company_blacklist", [])
        self.title_blacklist = parameters.get("title_blacklist", [])
        self.title_blacklist_set = set(word.lower().strip() for word in self.title_blacklist)
        self.company_blacklist_set = set(word.lower().strip() for word in self.company_blacklist)
        
        # Set the positions and locations
        self.searches = parameters.get("searches", [])
        
        self.apply_once_at_company = parameters.get("apply_once_at_company", False)
        self.base_search_url = self.get_base_search_url(parameters)
        self.seen_jobs = []
        
        job_applicants_threshold = parameters.get("job_applicants_threshold", {})
        self.min_applicants = job_applicants_threshold.get("min_applicants", 0)
        self.max_applicants = job_applicants_threshold.get("max_applicants", float("inf"))
        
        # Use resume_manager to get the resume path
        self.resume_manager = resume_manager
        self.resume_path = self.resume_manager.get_resume()
        self.output_file_directory = Path(parameters["outputFileDirectory"])
        self.env_config = EnvironmentKeys()
        
        self.cache = JobCache(self.output_file_directory)
        
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
            self.resume_manager,
            self.set_old_answers,
            self.gpt_answerer,
            self.resume_generator_manager,
            cache=self.cache,
        )
        
        for search in self.searches:
            search_country = search['location']
            search_terms = search['positions']
            
            for search_term in search_terms:
                job_page_number = -1
                logger.debug(f"Starting the search for '{search_term}' in '{search_country}'.")
        
                try:
                    while True:
                        job_page_number += 1
                        logger.info(f"Navigating to job page {job_page_number} for position '{search_term}' in '{search_country}'.")
                        self.next_job_page(search_term, search_country, job_page_number)
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
                            self.apply_jobs(search_term, search_country)
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
                utils.capture_screenshot(self.driver, "job_elements_timeout")
                logger.debug(f"HTML of the page: {self.driver.page_source}")
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
                locator = (By.CLASS_NAME, 'jobs-search-results-list')
                job_list_container = self.wait.until(
                    EC.presence_of_element_located(locator)
                )
                logger.debug("Job list container found.")

                # Scroll otimizado para carregar todos os elementos de trabalho
                logger.debug("Initiating optimized scroll to load all job elements.")
                self.scroll_jobs()
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
            # Take a screenshot for debugging
            utils.capture_screenshot(self.driver, "job_elements_error")
            return []

    def apply_jobs(self, search_term, search_country):
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
            Job(*self.extract_job_information_from_tile(job_element), search_term=search_term, search_country=search_country)
            for job_element in job_list_elements
        ]

        for job in job_list:
            logger.debug(f"Evaluating job: '{job.title}' at '{job.company}'")

            # Check if the job must be skipped
            if self.must_be_skipped(job):
                logger.debug(f"Skipping job based on blacklist: {job.link}")
                continue 

            # Check if the job has already been scored
            if USE_JOB_SCORE:
                if self.cache.is_in_job_score(job.link):
                    logger.debug(f"Job already scored: '{job.title}' at '{job.company}'.")
                    job.score = self.get_existing_score(job)
                
            try:
                if self.easy_applier_component.main_job_apply(job):
                    self.cache.write_to_file(job, "success")
                    self.cache.add_to_cache(job, 'success')
                    logger.info(f"Applied: {job.link}")

            except Exception as e:
                logger.error(
                        f"Failed to apply for job: Title='{job.title}', Company='{job.company}', "
                        f"Location='{job.location}', Link='{job.link}', Job State='{job.state}', Apply Method='{job.apply_method}', "
                        f"Error: {e}"
                    )

            # Add job link to seen jobs set
            # self.seen_jobs.append(job.link)
            self.cache.add_to_cache(job, "is_seen")

    def scroll_jobs(
        self,
        step=300, 
        reverse=False, 
        max_attempts=10,
    ):
        """
        Scrolls a scrollable job listings element on the page to load all job postings.

        Parameters:
        - step (int): Number of pixels to scroll at each step. Must be positive.
        - reverse (bool): If True, scrolls up; otherwise, scrolls down.
        - max_attempts (int): Maximum number of attempts without new items before stopping.

        Returns:
        - bool: True if scrolling completed successfully, False otherwise.
        """
        logger.debug("Starting scroll_jobs.")

        # Define locators
        jobs_list_locator = (By.CLASS_NAME, 'jobs-search-results-list')
        loader_locator = (By.CLASS_NAME, 'artdeco-loader')
        job_title_locator = (By.XPATH, ".//a[contains(@class, 'job-card-list__title')]")

        if step <= 0:
            logger.error("The step value must be positive.")
            raise ValueError("Step must be positive.")

        try:
            # Wait for the initial loader to disappear
            loader_disappeared = self.wait_for_loader(loader_locator)
            if not loader_disappeared:
                logger.debug("Initial loader did not disappear. Proceeding anyway.")

            # Locate the scrollable jobs list
            try:
                scrollable_element = self.wait.until(
                    EC.visibility_of_element_located(jobs_list_locator)
                )
                logger.debug("Scrollable jobs list is visible.")
            except TimeoutException:
                logger.warning(f"Jobs list with locator {jobs_list_locator} not found within the wait time.")
                return False

            # Wait for loader to disappear after locating the jobs list
            loader_disappeared = self.wait_for_loader(loader_locator)
            if not loader_disappeared:
                logger.debug("Loader did not disappear after locating jobs list. Proceeding.")

            # Check if the jobs list is scrollable
            try:
                scroll_height = int(scrollable_element.get_attribute("scrollHeight"))
                client_height = int(scrollable_element.get_attribute("clientHeight"))
                if scroll_height <= client_height:
                    logger.info("Jobs list is not scrollable.")
                    utils.capture_screenshot("jobs_list_not_scrollable")
                    return False
                logger.debug(f"Jobs list is scrollable (scrollHeight: {scroll_height}, clientHeight: {client_height}).")
            except Exception as e:
                logger.error(f"Failed to determine if jobs list is scrollable: {e}", exc_info=True)
                return False

            # Ensure the jobs list is visible
            if not scrollable_element.is_displayed():
                logger.warning("Jobs list is not visible. Attempting to bring it into view.")
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", scrollable_element)
                    time.sleep(1)  # Allow time for the element to become visible
                    if not scrollable_element.is_displayed():
                        logger.warning("Jobs list is still not visible after scrolling into view.")
                        utils.capture_screenshot("jobs_list_not_visible_after_scroll")
                        return False
                    logger.debug("Jobs list is now visible after scrolling into view.")
                except WebDriverException as e:
                    logger.error(f"Failed to scroll jobs list into view: {e}", exc_info=True)
                    utils.capture_screenshot("scroll_into_view_failed")
                    return False

            # Initialize counters for tracking job items and attempts
            previous_job_count = 0
            attempts = 0

            while attempts < max_attempts:
                # Wait for loader to disappear before scrolling
                loader_disappeared = self.wait_for_loader(loader_locator)
                if not loader_disappeared:
                    logger.debug("Loader did not disappear before scrolling. Proceeding.")

                # Calculate new scroll position
                try:
                    current_scroll_position = int(scrollable_element.get_attribute("scrollTop"))
                except (TypeError, ValueError) as e:
                    logger.error(f"Invalid scroll position value: {e}", exc_info=True)
                    return False

                new_scroll_position = current_scroll_position + step if not reverse else current_scroll_position - step
                self.driver.execute_script("arguments[0].scrollTop = arguments[1];", scrollable_element, new_scroll_position)
                logger.debug(f"Scrolled to position: {new_scroll_position}")

                # Wait for loader to disappear after scrolling
                loader_disappeared = self.wait_for_loader(loader_locator)
                if not loader_disappeared:
                    logger.debug("Loader is still visible after scrolling. Proceeding.")

                # Retrieve current number of job items
                job_items = self.driver.find_elements(*job_title_locator)
                current_job_count = len(job_items)
                logger.debug(f"Current number of job items: {current_job_count}")

                # Check if enough job items are loaded
                if current_job_count >= 25:
                    logger.debug("Reached 25 job items.")
                    break

                if current_job_count > previous_job_count:
                    logger.debug("New job items loaded.")
                    previous_job_count = current_job_count
                    attempts = 0  # Reset attempts since new items were found
                else:
                    attempts += 1
                    logger.debug(f"No new job items detected. Attempt {attempts}/{max_attempts}.")
                    time.sleep(0.5)  # Wait before the next attempt

            logger.debug("Completed scrolling. All job items have been loaded.")
            return True

        except Exception as e:
            logger.error(f"An error occurred during scrolling jobs: {e}", exc_info=True)
            return False

    def wait_for_loader(self, loader_locator, timeout=10):
        """
        Waits for the loader element to disappear.

        Parameters:
        - loader_locator (tuple): Locator for the loader element.
        - timeout (int): Maximum time to wait in seconds.

        Returns:
        - bool: True if the loader disappeared, False otherwise.
        """
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.invisibility_of_element_located(loader_locator)
            )
            logger.debug("Loader has disappeared.")
            return True
        except TimeoutException:
            logger.warning("Loader did not disappear within the specified timeout.")
            return False


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

    def next_job_page(self, position: str, search_country: str, job_page: int):
        """
        Navigates to the specified job page based on the job position and location.

        Args:
            position (str): The job position to search for.
            search_country (str): The location/country to search in.
            job_page (int): The page number to navigate to.
        """
        try:
            # Construct query parameters
            start = job_page * 25  # Assuming 25 jobs per page

            #location 
            if search_country == "Worldwide":
                location_url = "&geoId=92000000"
            elif search_country == "United States":
                location_url = "&geoId=103644278"
            else:
                location_url = f"&location=" + search_country
            
            # Build the full URL using base_search_url and query parameters
            url = (
                f"https://www.linkedin.com/jobs/search/{self.base_search_url}"
                f"&keywords={position}{location_url}&start={start}"
            )

            # Log the navigation details for debugging
            logger.debug(
                f"Navigating to job page: Position='{position}', "
                f"Location='{search_country}', Page={job_page}, URL='{url}'."
            )

            # Navigate to the constructed URL
            self.driver.get(url)

        except WebDriverException as wd_exc:
            # Handle Selenium-specific exceptions
            logger.error(
                f"Selenium WebDriverException occurred while navigating to page {job_page} "
                f"for position '{position}' in '{search_country}': {wd_exc}",
                exc_info=True
            )
            utils.capture_screenshot(self.driver, f"webdriver_error_page_{job_page}")

        except Exception as exc:
            # Handle any other unexpected exceptions
            logger.error(
                f"Unexpected error occurred while navigating to page {job_page} "
                f"for position '{position}' in '{search_country}': {exc}",
                exc_info=True
            )
            utils.capture_screenshot(self.driver, f"unexpected_error_page_{job_page}")

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
            EC.presence_of_element_located((By.XPATH, ".//a[contains(@class, 'job-card-list__title')]")))
            job_title = job_title_element.text.strip()
            logger.debug(f"Extracted Job Title: '{job_title}'")
        except NoSuchElementException:
            logger.error("Job title element not found.")
            logger.debug(f"HTML do job_tile: {job_tile.get_attribute('outerHTML')}")
            utils.capture_screenshot(self.driver, "job_title_error")
        except TimeoutException:
            logger.error("Timed out waiting for the job title element.")
            logger.debug(f"HTML do job_tile: {job_tile.get_attribute('outerHTML')}")
            utils.capture_screenshot(self.driver, "job_title_error")

        except Exception as e:
            logger.error(f"Unexpected error in _extract_job_title: {e}", exc_info=True)
            logger.debug(f"HTML do job_tile: {job_tile.get_attribute('outerHTML')}")
            utils.capture_screenshot(self.driver, "job_title_error")
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

        # Check if the link has already been seen
        if self.cache.is_in_is_seen(link):
            logger.debug(f"Skipping by seen link: {link}")
            return True
       
        # Check if the job has already been skipped
        if self.cache.is_in_skipped_low_salary(job.link):
            logger.debug(f"Job has already been skipped for low salary: {job.link}")
            return True
        
        # Check if the job has already been skipped
        if self.cache.is_in_skipped_low_score(job.link):
            logger.debug(f"Job has already been skipped for low score: {job.link}")
            return True
        
        # Check if the job has already been applied
        if self.cache.is_in_success(job.link):
            logger.debug(f"Job has already been applied: {job.link}")
            return True
        
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