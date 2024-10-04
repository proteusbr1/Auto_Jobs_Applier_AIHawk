import json
import os
import random
import time
from itertools import product
from pathlib import Path
from datetime import datetime

from inputimeout import inputimeout, TimeoutOccurred
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

import src.utils as utils
from app_config import MINIMUM_WAIT_TIME
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
    def __init__(self, driver):
        logger.debug("Initializing AIHawkJobManager")
        self.driver = driver
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
        minimum_time = MINIMUM_WAIT_TIME
        minimum_page_time = time.time() + minimum_time

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
                    time.sleep(random.uniform(1.5, 3.5))
                    logger.debug("Initiating the application process for this page.")

                    try:
                        jobs = self.get_jobs_from_page()
                        if not jobs:
                            logger.info("No more jobs found on this page. Exiting loop.")
                            break
                    except Exception as e:
                        logger.error("Failed to retrieve jobs.", exc_info=True)
                        break

                    try:
                        self.apply_jobs(position)
                    except Exception as e:
                        logger.error("Error during job application.", exc_info=True)
                        continue

                    logger.info("Completed applying to jobs on this page.")

                    time_left = minimum_page_time - time.time()

                    # Ask user if they want to skip waiting, with timeout
                    if time_left > 0:
                        try:
                            user_input = inputimeout(
                                prompt=f"Sleeping for {time_left:.0f} seconds. Press 'y' to skip waiting. Timeout 60 seconds: ",
                                timeout=0
                            ).strip().lower()
                        except TimeoutOccurred:
                            user_input = ''  # No input after timeout
                        if user_input == 'y':
                            logger.info("User chose to skip waiting.")
                        else:
                            logger.debug(f"Sleeping for {time_left:.0f} seconds as user chose not to skip.")
                            time.sleep(time_left)

                    minimum_page_time = time.time() + minimum_time

                    if page_sleep % 5 == 0:
                        sleep_time = 0
                        # sleep_time = random.randint(5, 34)
                        try:
                            user_input = inputimeout(
                                prompt=f"Sleeping for {sleep_time / 60:.2f} minutes. Press 'y' to skip waiting. Timeout 60 seconds: ",
                                timeout=0
                            ).strip().lower()
                        except TimeoutOccurred:
                            user_input = ''  # No input after timeout
                        if user_input == 'y':
                            logger.info("User chose to skip waiting.")
                        else:
                            logger.debug(f"Sleeping for {sleep_time} seconds.")
                            time.sleep(sleep_time)
                        page_sleep += 1
            except Exception as e:
                logger.error("Unexpected error during job search.", exc_info=True)
                continue

            time_left = minimum_page_time - time.time()

            if time_left > 0:
                try:
                    user_input = inputimeout(
                        prompt=f"Sleeping for {time_left:.0f} seconds. Press 'y' to skip waiting. Timeout 60 seconds: ",
                        timeout=0
                    ).strip().lower()
                except TimeoutOccurred:
                    user_input = ''  # No input after timeout
                if user_input == 'y':
                    logger.info("User chose to skip waiting.")
                else:
                    logger.debug(f"Sleeping for {time_left:.0f} seconds as user chose not to skip.")
                    time.sleep(time_left)

            minimum_page_time = time.time() + minimum_time

            if page_sleep % 5 == 0:
                sleep_time = 0
                # sleep_time = random.randint(50, 90)
                try:
                    user_input = inputimeout(
                        prompt=f"Sleeping for {sleep_time / 60:.2f} minutes. Press 'y' to skip waiting: ",
                        timeout=0
                    ).strip().lower()
                except TimeoutOccurred:
                    user_input = ''  # No input after timeout
                if user_input == 'y':
                    logger.info("User chose to skip waiting.")
                else:
                    logger.debug(f"Sleeping for {sleep_time} seconds.")
                    time.sleep(sleep_time)
                page_sleep += 1

    def get_jobs_from_page(self):

        try:

            no_jobs_element = self.driver.find_element(By.CLASS_NAME, 'jobs-search-two-pane__no-results-banner--expand')
            if 'No matching jobs found' in no_jobs_element.text or 'unfortunately, things aren' in self.driver.page_source.lower():
                logger.info("No matching jobs found on this page, skipping.")
                return []

        except NoSuchElementException:
            logger.debug("No 'no results' banner found on the page.")

        try:
            job_results = self.driver.find_element(By.CLASS_NAME, "jobs-search-results-list")
            utils.scroll_slow(self.driver, job_results)
            utils.scroll_slow(self.driver, job_results, step=300, reverse=True)

            job_list_elements = self.driver.find_elements(By.CLASS_NAME, 'scaffold-layout__list-container')[
                0].find_elements(By.CLASS_NAME, 'jobs-search-results__list-item')
            if not job_list_elements:
                logger.info("No job list elements found on page, skipping.")
                return []

            return job_list_elements

        except NoSuchElementException:
            logger.warning("No job results found on the page.")
            return []

        except Exception as e:
            logger.error("Error while fetching job elements.", exc_info=True)
            return []

    def apply_jobs(self, position):
        try:
            no_jobs_element = self.driver.find_element(By.CLASS_NAME, 'jobs-search-two-pane__no-results-banner--expand')
            if 'No matching jobs found' in no_jobs_element.text or 'unfortunately, things aren' in self.driver.page_source.lower():
                logger.info("No matching jobs found on this page, skipping.")
                return
        except NoSuchElementException:
            logger.debug("No 'no results' banner found.")

        job_list_elements = self.driver.find_elements(By.CLASS_NAME, 'scaffold-layout__list-container')[
            0].find_elements(By.CLASS_NAME, 'jobs-search-results__list-item')

        if not job_list_elements:
            logger.info("No job list elements found on page, skipping.")
            return

        job_list = [
            Job(*self.extract_job_information_from_tile(job_element), position=position)
            for job_element in job_list_elements
        ]

        for job in job_list:

            logger.debug(f"Starting applicant for job: '{job.title}' at '{job.company}'")
            # TODO fix apply threshold
            """
                # Initialize applicants_count as None
                applicants_count = None

                # Iterate over each job insight element to find the one containing the word "applicant"
                for element in job_insight_elements:
                    logger.debug(f"Checking element text: {element.text}")
                    if "applicant" in element.text.lower():
                        # Found an element containing "applicant"
                        applicants_text = element.text.strip()
                        logger.debug(f"Applicants text found: {applicants_text}")

                        # Extract numeric digits from the text (e.g., "70 applicants" -> "70")
                        applicants_count = ''.join(filter(str.isdigit, applicants_text))
                        logger.debug(f"Extracted applicants count: {applicants_count}")

                        if applicants_count:
                            if "over" in applicants_text.lower():
                                applicants_count = int(applicants_count) + 1  # Handle "over X applicants"
                                logger.debug(f"Applicants count adjusted for 'over': {applicants_count}")
                            else:
                                applicants_count = int(applicants_count)  # Convert the extracted number to an integer
                        break

                # Check if applicants_count is valid (not None) before performing comparisons
                if applicants_count is not None:
                    # Perform the threshold check for applicants count
                    if applicants_count < self.min_applicants or applicants_count > self.max_applicants:
                        logger.debug(f"Skipping '{job.title}' at '{job.company}', applicants count: {applicants_count}")
                        self.write_to_file(job, "skipped_due_to_applicants")
                        continue  # Skip this job if applicants count is outside the threshold
                    else:
                        logger.debug(f"Applicants count {applicants_count} is within the threshold")
                else:
                    # If no applicants count was found, log a warning but continue the process
                    logger.warning(
                        f"Applicants count not found for '{job.title}' at '{job.company}', continuing with application.")
            except NoSuchElementException:
                # Log a warning if the job insight elements are not found, but do not stop the job application process
                logger.warning(
                    f"Applicants count elements not found for '{job.title}' at '{job.company}', continuing with application.")
            except ValueError as e:
                # Handle errors when parsing the applicants count
                logger.error(f"Error parsing applicants count for '{job.title}' at '{job.company}': {e}", exc_info=True)
            except Exception as e:
                # Catch any other exceptions to ensure the process continues
                logger.error(
                    f"Unexpected error during applicants count processing for '{job.title}' at '{job.company}': {e}", exc_info=True)

            # Continue with the job application process regardless of the applicants count check
"""
            if self.is_blacklisted(job.title, job.company, job.link):
                logger.debug(f"Job blacklisted: '{job.title}' at '{job.company}'.")
                self.write_to_file(job, "skipped")
                continue
            if self.is_already_applied_to_job(job.title, job.company, job.link):
                logger.debug(f"Already applied to job: '{job.title}' at '{job.company}'.")
                self.write_to_file(job, "skipped")
                continue
            if self.is_already_applied_to_company(job.company):
                logger.debug(f"Already applied to company: '{job.company}'.")
                self.write_to_file(job, "skipped")
                continue
            try:
                if job.apply_method not in {"Continue", "Applied", "Apply"}:
                    if self.easy_applier_component.job_apply(job):
                        self.write_to_file(job, "success")
                        logger.info(f"Successfully applied to job: '{job.title}' at '{job.company}'.")
                    else:
                        self.write_to_file(job, "skipped")
                        logger.debug(f"Skipped to apply for '{job.title}' at '{job.company}'.")
            except Exception as e:
                logger.error(f"Failed to apply for '{job.title}' at '{job.company}': {e}", exc_info=True)
                self.write_to_file(job, "failed")
                continue

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
            "job_recruiter": job.recruiter_link,
            "job_location": job.location,
            "pdf_path": pdf_path,
            # "timestamp": current_time  # Adds the date and time of the entry
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
        logger.debug("Extracting job information from tile.")
        job_title, company, job_location, link, apply_method = "", "", "", "", ""
        try:
            job_title = job_tile.find_element(By.CLASS_NAME, 'job-card-list__title').find_element(By.TAG_NAME, 'strong').text
            link = job_tile.find_element(By.CLASS_NAME, 'job-card-list__title').get_attribute('href').split('?')[0]
            company = job_tile.find_element(By.CLASS_NAME, 'job-card-container__primary-description').text
            logger.debug(f"Job information extracted: Title='{job_title}', Company='{company}'.")
        except NoSuchElementException:
            logger.warning("Some job information (title, link, or company) is missing.")
        try:
            job_location = job_tile.find_element(By.CLASS_NAME, 'job-card-container__metadata-item').text
            logger.debug(f"Job location extracted: '{job_location}'.")
        except NoSuchElementException:
            logger.warning("Job location is missing.")
        try:
            apply_method = job_tile.find_element(By.CLASS_NAME, 'job-card-container__apply-method').text
            logger.debug(f"Apply method extracted: '{apply_method}'.")
        except NoSuchElementException:
            apply_method = "Applied"
            logger.warning("Apply method not found, assuming 'Applied'.")

        return job_title, company, job_location, link, apply_method

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