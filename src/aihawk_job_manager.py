import json
import os
import random
import time
from itertools import product
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Any, Tuple

from inputimeout import inputimeout, TimeoutOccurred
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException 
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import src.utils as utils
from app_config import MINIMUM_WAIT_TIME, MINIMUM_SCORE_JOB_APPLICATION, USER_RESUME_SUMMARY
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
        logger.debug("AIHawkJobManager initialized successfully")

    def set_parameters(self, parameters):
        logger.info("Setting parameters for AIHawkJobManager")
        self.company_blacklist = [company.lower() for company in parameters.get('company_blacklist', [])] or []
        self.title_blacklist = [word.lower() for word in parameters.get('title_blacklist', [])] or []
        self.positions = parameters.get('positions', [])
        self.locations = parameters.get('locations', [])
        self.apply_once_at_company = parameters.get('apply_once_at_company', False)
        self.base_search_url = self.get_base_search_url(parameters)
        self.seen_jobs = []

        job_applicants_threshold = parameters.get('job_applicants_threshold', {})
        self.min_applicants = job_applicants_threshold.get('min_applicants', 0)
        self.max_applicants = job_applicants_threshold.get('max_applicants', float('inf'))

        resume_path = parameters.get('uploads', {}).get('resume', None)
        self.resume_path = Path(resume_path) if resume_path and Path(resume_path).exists() else None
        self.output_file_directory = Path(parameters['outputFileDirectory'])
        self.env_config = EnvironmentKeys()
        logger.debug("Parameters set successfully")

    def set_gpt_answerer(self, gpt_answerer):
        logger.debug("Setting GPT answerer")
        self.gpt_answerer = gpt_answerer

    def set_resume_generator_manager(self, resume_generator_manager):
        logger.debug("Setting resume generator manager")
        self.resume_generator_manager = resume_generator_manager

    def start_applying(self):
        logger.info("Starting job application process")
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
                    logger.info("No matching jobs found on this search.")
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
                    logger.info("No job elements found on the page, skipping.")
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
        except TimeoutException:
            logger.warning("Timed out waiting for job list container.")
            return
        except NoSuchElementException:
            logger.info("No job list elements found on page, skipping.")
            return

        if not job_list_elements:
            logger.info("No job list elements found on page, skipping.")
            return

        job_list = [
            Job(*self.extract_job_information_from_tile(job_element), position=position)
            for job_element in job_list_elements
        ]

        for job in job_list:
            logger.debug(f"Evaluating job: '{job.title}' at '{job.company}'")
            
            # Check if the job is blacklisted
            if self.is_blacklisted(job.title, job.company, job.link):
                logger.debug(f"Job blacklisted: '{job.title}' at '{job.company}'.")
                continue
            
            # Check if already applied to the job
            if self.is_already_applied_to_job(job.title, job.company, job.link):
                logger.debug(f"Already applied to job: '{job.title}' at '{job.company}'.")
                continue
            
            # Check if already applied to the company
            if self.is_already_applied_to_company(job.company):
                logger.debug(f"Already applied to company: '{job.company}'.")
                continue
            
            # Check if the job has already been scored
            if self.is_already_scored(job.title, job.company, job.link):
                logger.debug(f"Job already scored: '{job.title}' at '{job.company}'.")
                job.score = self.get_existing_score(job.title, job.company, job.link)
            # else:
            #     # Evaluate the job score if it hasn't been scored yet
            #     job.score = self.evaluate_job(job.description, USER_RESUME_SUMMARY, self.gpt_answerer)

            # Check if the score is high enough to apply or if score is None (not yet scored)
            if job.score is None or job.score >= MINIMUM_SCORE_JOB_APPLICATION:
                try:
                    if job.apply_method not in {"Continue", "Applied", "Apply"}:
                        if self.easy_applier_component.job_apply(job):
                            self.write_to_file(job, "success")
                            self.write_job_score(job, job.score)
                            logger.info(f"Successfully applied to job: '{job.title}' at '{job.company}'.")
                        else:
                            self.write_to_file(job, "skipped")
                            logger.debug(f"Skipped applying for '{job.title}' at '{job.company}'.")
                except Exception as e:
                    logger.error(f"Failed to apply for '{job.title}' at '{job.company}': {e}", exc_info=True)
                    self.write_to_file(job, "failed")
            else:
                logger.debug(f"Job score is {job.score}. Skipping application for job: '{job.title}' at '{job.company}'.")
                # self.write_to_file(job, "skipped")
                self.write_job_score(job, job.score)

    def get_existing_score(self, job_title, company, link):
        """
        Retrieves the existing score for the job from the job_score.json file.
        """
        file_path = self.output_file_directory / 'job_score.json'
        
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

    def write_to_file(self, job, file_name):
        logger.debug(f"Writing job application result to file: '{file_name}'.")
        pdf_path = Path(job.pdf_path).resolve()
        pdf_path = pdf_path.as_uri()
        
        # Get current date and time
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        data = {
            "company": job.company,
            "job_title": job.title,
            "link": job.link,
            "score": job.score,  
            "job_recruiter": job.recruiter_link,
            "job_location": job.location,
            "pdf_path": pdf_path,
            "timestamp": current_time
        }
        
        file_path = self.output_file_directory / f"{file_name}.json"
        
        if not file_path.exists():
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump([data], f, indent=4)
                logger.debug(f"Job data written to new file: '{file_name}'.")
            except Exception as e:
                logger.error(f"Failed to write to new file '{file_name}': {e}", exc_info=True)
        else:
            try:
                with open(file_path, 'r+', encoding='utf-8') as f:
                    try:
                        existing_data = json.load(f)
                    except json.JSONDecodeError:
                        logger.error(f"JSON decode error in file: {file_path}. Initializing with empty list.")
                        existing_data = []
                    
                    existing_data.append(data)
                    f.seek(0)
                    json.dump(existing_data, f, indent=4)
                    f.truncate()
                logger.debug(f"Job data appended to existing file: '{file_name}'.")
            except Exception as e:
                logger.error(f"Failed to append to file '{file_name}': {e}", exc_info=True)

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
            Tuple[str, str, str, str, str]: A tuple containing job_title, company, job_location, link, apply_method.
        """
        logger.debug("Starting extraction of job information from tile.")

        # Initialize variables
        job_title, company, link = self._extract_title_company_link(job_tile)
        job_location = self._extract_job_location(job_tile)
        apply_method = self._extract_apply_method(job_tile)

        logger.debug(
            f"Completed extraction: Title='{job_title}', Company='{company}', "
            f"Location='{job_location}', Link='{link}', Apply Method='{apply_method}'"
        )

        return job_title, company, job_location, link, apply_method

    def _extract_title_company_link(self, job_tile):
        """
        Extracts the job title, company, and link from the job tile.

        Args:
            job_tile (WebElement): The Selenium WebElement representing the job tile.

        Returns:
            Tuple[str, str, str]: A tuple containing job_title, company, link.
        """
        job_title = ""
        company = ""
        link = ""
        try:
            job_title_element = self.wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, 'job-card-list__title'))
            )
            job_title = job_title_element.find_element(By.TAG_NAME, 'strong').text
            link = job_title_element.get_attribute('href').split('?')[0]
            company = job_tile.find_element(By.CLASS_NAME, 'job-card-container__primary-description').text
            logger.debug(f"Extracted Job Title: '{job_title}', Company: '{company}', Link: '{link}'")
        except (NoSuchElementException, TimeoutException) as e:
            logger.error(f"Failed to extract job title, link, or company. Exception: {e}")
            logger.error(f"Job tile HTML for debugging: {job_tile.get_attribute('outerHTML')}")
        return job_title, company, link

    def _extract_job_location(self, job_tile):
        """
        Extracts the job location from the job tile.

        Args:
            job_tile (WebElement): The Selenium WebElement representing the job tile.

        Returns:
            str: The job location.
        """
        job_location = ""
        try:
            job_location_element = self.wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, 'job-card-container__metadata-item'))
            )
            job_location = job_location_element.text
            logger.debug(f"Extracted Job Location: '{job_location}'")
        except (NoSuchElementException, TimeoutException) as e:
            logger.warning(f"Failed to extract job location. Exception: {e}")
        return job_location

    def _extract_apply_method(self, job_tile):
        """
        Extracts the apply method from the job tile using CSS selectors.

        Args:
            job_tile (WebElement): The Selenium WebElement representing the job tile.

        Returns:
            str: The apply method.
        """
        apply_method = ""
        try:
            # Try the latest CSS selector first
            try:
                apply_method_element = self.wait.until(
                    EC.presence_of_element_located((By.CLASS_NAME, 'job-card-container__footer-job-state'))
                )
                apply_method = apply_method_element.text
                logger.debug(f"Extracted Apply Method from 'job-card-container__footer-job-state': '{apply_method}'")
            except TimeoutException:
                # Fallback to older selector if latest not found
                apply_method_element = self.wait.until(
                    EC.presence_of_element_located((By.CLASS_NAME, 'job-card-container__apply-method'))
                )
                apply_method = apply_method_element.text
                logger.debug(f"Extracted Apply Method from 'job-card-container__apply-method': '{apply_method}'")
        except (NoSuchElementException, TimeoutException) as e:
            apply_method = "Applied"  # Default value if both selectors fail
            logger.error(f"Failed to extract apply method from both CSS classes. Assuming 'Applied'. Exception: {e}")
            logger.error(f"Job tile HTML for debugging: {job_tile.get_attribute('outerHTML')}")
        return apply_method


    def is_blacklisted(self, job_title, company, link):
        logger.debug(f"Checking if job is blacklisted: Title='{job_title}', Company='{company}'.")
        job_title_words = job_title.lower().split(' ')
        title_blacklisted = any(word in self.title_blacklist for word in job_title_words)
        company_blacklisted = company.strip().lower() in (word.strip().lower() for word in self.company_blacklist)
        link_seen = link in self.seen_jobs
        is_blacklisted = title_blacklisted or company_blacklisted or link_seen
        logger.debug(f"Job blacklisted status: {is_blacklisted}")

        return is_blacklisted

    def is_already_applied_to_job(self, job_title, company, link):
        link_seen = link in self.seen_jobs
        if link_seen:
            logger.debug(f"Already applied to job: Title='{job_title}', Company='{company}', Link='{link}'.")
        return link_seen

    def is_already_applied_to_company(self, company):
        if not self.apply_once_at_company:
            return False

        output_files = ["success.json"]
        for file_name in output_files:
            file_path = self.output_file_directory / file_name
            if file_path.exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        for applied_job in existing_data:
                            if applied_job['company'].strip().lower() == company.strip().lower():
                                logger.info(f"Already applied at '{company}' (once per company policy). Skipping.")
                                return True
                except json.JSONDecodeError:
                    logger.error(f"JSON decode error in file: {file_path}. Skipping file.")
                    continue
        return False
    
    def is_already_scored(self, job_title, company, link):
        """
        Checks if the job has already been scored (skipped previously) and is in the job_score.json file.
        """
        logger.debug(f"Checking if job is already scored: Title='{job_title}', Company='{company}'.")
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

    def write_job_score(self, job: Any, score: float):
        """
        Saves jobs that were not applied to avoid future GPT queries, including the score and timestamp.
        """
        logger.debug(f"Saving skipped job: {job.title} at {job.company} with score {score}")
        file_path = self.output_file_directory / 'job_score.json'

        # Get current date and time
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Data format to be saved
        job_data = {
            "search_term": job.position, 
            "company": job.company,
            "job_title": job.title,
            "link": job.link,
            "score": score,  # Adds the score to the record
            "timestamp": current_time  # Adds the timestamp
        }

        # Check if file exists, if not, create a new one
        if not file_path.exists():
            try:
                with open(file_path, 'w') as f:
                    json.dump([job_data], f, indent=4)
                logger.debug(f"Created new job_score.json with job: {job.title}")
            except Exception as e:
                logger.error(f"Failed to create job_score.json: {e}", exc_info=True)
                raise
        else:
            # If it exists, load existing data and append the new job
            try:
                with open(file_path, 'r+') as f:
                    try:
                        existing_data = json.load(f)
                        if not isinstance(existing_data, list):
                            logger.warning("job_score.json format is incorrect. Overwriting with a new list.")
                            existing_data = []
                    except json.JSONDecodeError:
                        logger.warning("job_score.json is empty or corrupted. Initializing with an empty list.")
                        existing_data = []
                    
                    existing_data.append(job_data)
                    f.seek(0)
                    json.dump(existing_data, f, indent=4)
                    f.truncate()
                logger.debug(f"Appended job to job_score.json: {job.title}")
            except Exception as e:
                logger.error(f"Failed to append job to job_score.json: {e}", exc_info=True)
                raise
        logger.debug(f"Job saved successfully: {job.title} with score {score}")