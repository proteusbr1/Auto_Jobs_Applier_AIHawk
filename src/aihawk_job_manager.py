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
        # minimum_time = MINIMUM_WAIT_TIME
        # minimum_page_time = time.time() + minimum_time

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

                    logger.info("Completed applying to jobs on this page.")

                    # time_left = minimum_page_time - time.time()

                    # Ask user if they want to skip waiting, with timeout
                    # if time_left > 0:
                    #     try:
                    #         user_input = inputimeout(
                    #             prompt=f"Sleeping for {time_left:.0f} seconds. Press 'y' to skip waiting. Timeout 60 seconds: ",
                    #             timeout=0
                    #         ).strip().lower()
                    #     except TimeoutOccurred:
                    #         user_input = ''  # No input after timeout
                    #     if user_input == 'y':
                    #         logger.info("User chose to skip waiting.")
                    #     else:
                    #         logger.debug(f"Sleeping for {time_left:.0f} seconds as user chose not to skip.")
                    #         time.sleep(time_left)

                    # minimum_page_time = time.time() + minimum_time

                    # if page_sleep % 5 == 0:
                    #     sleep_time = 0
                    #     # sleep_time = random.randint(5, 34)
                    #     try:
                    #         user_input = inputimeout(
                    #             prompt=f"Sleeping for {sleep_time / 60:.2f} minutes. Press 'y' to skip waiting. Timeout 60 seconds: ",
                    #             timeout=0
                    #         ).strip().lower()
                    #     except TimeoutOccurred:
                    #         user_input = ''  # No input after timeout
                    #     if user_input == 'y':
                    #         logger.info("User chose to skip waiting.")
                    #     else:
                    #         logger.debug(f"Sleeping for {sleep_time} seconds.")
                    #         time.sleep(sleep_time)
                    #     page_sleep += 1
            except Exception as e:
                logger.error("Unexpected error during job search.", exc_info=True)
                continue

            # time_left = minimum_page_time - time.time()

            # if time_left > 0:
            #     try:
            #         user_input = inputimeout(
            #             prompt=f"Sleeping for {time_left:.0f} seconds. Press 'y' to skip waiting. Timeout 60 seconds: ",
            #             timeout=0
            #         ).strip().lower()
            #     except TimeoutOccurred:
            #         user_input = ''  # No input after timeout
            #     if user_input == 'y':
            #         logger.info("User chose to skip waiting.")
            #     else:
            #         logger.debug(f"Sleeping for {time_left:.0f} seconds as user chose not to skip.")
            #         time.sleep(time_left)

            # minimum_page_time = time.time() + minimum_time

            # if page_sleep % 5 == 0:
            #     sleep_time = 0
            #     # sleep_time = random.randint(50, 90)
            #     try:
            #         user_input = inputimeout(
            #             prompt=f"Sleeping for {sleep_time / 60:.2f} minutes. Press 'y' to skip waiting: ",
            #             timeout=0
            #         ).strip().lower()
            #     except TimeoutOccurred:
            #         user_input = ''  # No input after timeout
            #     if user_input == 'y':
            #         logger.info("User chose to skip waiting.")
            #     else:
            #         logger.debug(f"Sleeping for {sleep_time} seconds.")
            #         time.sleep(sleep_time)
            #     page_sleep += 1

    def get_jobs_from_page(self):
        try:
            no_jobs_element = self.driver.find_element(By.CLASS_NAME, 'jobs-search-no-results-banner')
            if 'No matching jobs found' in no_jobs_element.text or 'unfortunately, things aren' in self.driver.page_source.lower():
                logger.info("No matching jobs found on this page, skipping.")
                return []
        except NoSuchElementException:
            logger.debug("No 'no results' banner found on the page.")
        
        try:
            job_results = self.driver.find_element(By.CLASS_NAME, "jobs-search-results-list")
            utils.scroll_slow(self.driver, job_results)
            utils.scroll_slow(self.driver, job_results, step=300, reverse=True)

            job_list_elements = self.driver.find_elements(By.CLASS_NAME, 'scaffold-layout__list-container')[0].find_elements(By.CLASS_NAME, 'jobs-search-results__list-item')
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


    # def evaluate_job(self, job_description: str, resume_prompt: str, gpt_answerer: Any) -> float:
    #     """
    #     Sends the job description and resume to an AI system (using gpt_answerer) and returns a score from 0 to 10
    #     """
    #     # Create the prompt to evaluate the job description and resume
    #     prompt = f"""
    #     You are a Human Resources expert specializing in evaluating job applications for the American job market. Your task is to assess the compatibility between the following job description and a provided resume. 
    #     Return only a score from 0 to 10 representing the candidate's likelihood of securing the position, with 0 being the lowest probability and 10 being the highest. 
    #     The assessment should consider HR-specific criteria for the American job market, including skills, experience, education, and any other relevant criteria mentioned in the job description.

    #     Job Description:
    #     {job_description}

    #     Resume:
    #     {resume_prompt}

    #     Score (0 to 10):
    #     """
        
    #     logger.debug("Sending job description and resume to GPT for evaluation")
    #     # Use the gpt_answerer to make the evaluation
    #     response = gpt_answerer.answer_question_textual_wide_range(prompt)
    #     logger.debug(f"Received response from GPT: {response}")
        
    #     # Process the response to extract the score
    #     try:
    #         # Extract the number (score) from GPT's response
    #         score = float(re.search(r"\d+(\.\d+)?", response).group(0))
    #         logger.info(f"Extracted score from GPT response: {score}")
    #         return score
    #     except (AttributeError, ValueError):
    #         logger.error(f"Error processing the score from response: {response}", exc_info=True)
    #         return 0.1  # Return 0.1 if a valid score cannot be extracted


    def apply_jobs(self, position):
        job_list_elements = self.driver.find_elements(By.CLASS_NAME, 'scaffold-layout__list-container')[0].find_elements(By.CLASS_NAME, 'jobs-search-results__list-item')

        if not job_list_elements:
            logger.info("No job list elements found on page, skipping.")
            return

        job_list = [
            Job(*self.extract_job_information_from_tile(job_element), position=position)
            for job_element in job_list_elements
        ]

        for job in job_list:
            logger.debug(f"Evaluating job: '{job.title}' at '{job.company}'")
            # logger.info(f"Job score is {score}. Proceeding to apply for job: '{job.title}' at '{job.company}'")
            # Proceed with the application process (existing logic)
            if self.is_blacklisted(job.title, job.company, job.link):
                logger.debug(f"Job blacklisted: '{job.title}' at '{job.company}'.")
                # self.write_to_file(job, "skipped")
                continue
            if self.is_already_applied_to_job(job.title, job.company, job.link):
                logger.debug(f"Already applied to job: '{job.title}' at '{job.company}'.")
                # self.write_to_file(job, "skipped")
                continue
            if self.is_already_applied_to_company(job.company):
                logger.debug(f"Already applied to company: '{job.company}'.")
                # self.write_to_file(job, "skipped")
                continue
            if self.is_already_scored(job.title, job.company, job.link):
                logger.debug(f"Job already scored: '{job.title}' at '{job.company}'.")
                # self.write_to_file(job, "skipped")
                continue
                
            # Call the evaluation function
            # job.score = self.evaluate_job(job.description, USER_RESUME_SUMMARY, self.gpt_answerer)

            # Check if the score is high enough to apply
            # if job.score >= MINIMUM_SCORE_JOB_APPLICATION:
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
                continue
            # else:
            #     logger.info(f"Job score is {job.score}. Skipping application for job: '{job.title}' at '{job.company}'.")
            #     self.write_to_file(job, "skipped")
            #     self.write_job_score(job, job.score)

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
        logger.debug("Extracting job information from tile.")
        job_title, company, job_location, link, apply_method = "", "", "", "", ""
        
        try:
            job_title = job_tile.find_element(By.CLASS_NAME, 'job-card-list__title').find_element(By.TAG_NAME, 'strong').text
            link = job_tile.find_element(By.CLASS_NAME, 'job-card-list__title').get_attribute('href').split('?')[0]
            company = job_tile.find_element(By.CLASS_NAME, 'job-card-container__primary-description').text
            logger.debug(f"Job information extracted: Title='{job_title}', Company='{company}', Link='{link}'")
        except NoSuchElementException as e:
            logger.warning(f"Failed to extract job title, link, or company: {e}")

        try:
            job_location = job_tile.find_element(By.CLASS_NAME, 'job-card-container__metadata-item').text
            logger.debug(f"Job location extracted: '{job_location}'.")
        except NoSuchElementException as e:
            logger.warning(f"Failed to extract job location: {e}")

        try:
            # Primeiro tenta encontrar o seletor da nova classe
            apply_method = job_tile.find_element(By.CLASS_NAME, 'job-card-container__footer-job-state').text
            logger.debug(f"Apply method extracted from '.job-card-container__footer-job-state': '{apply_method}'.")
        except NoSuchElementException as e:
            logger.debug(f"Failed to extract apply method from '.job-card-container__footer-job-state'. Exception: {e}")
            
            try:
                # Se falhar, tenta encontrar o seletor da classe anterior
                apply_method = job_tile.find_element(By.CLASS_NAME, 'job-card-container__apply-method').text
                logger.debug(f"Apply method extracted from '.job-card-container__apply-method': '{apply_method}'.")
            except NoSuchElementException as e:
                apply_method = "Applied"
                logger.warning(f"Failed to extract apply method from both CSS classes. Assuming 'Applied'. Exception: {e}")
                logger.warning(f"Job tile content for debugging: {job_tile.get_attribute('innerHTML')}")
                logger.warning(f"Job tile inner HTML for debugging: {job_tile.get_attribute('innerHTML')}")

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

    # def write_job_score(self, job: Any, score: float):
    #     """
    #     Saves jobs that were not applied to avoid future GPT queries, including the score and timestamp.
    #     """
    #     logger.debug(f"Saving skipped job: {job.title} at {job.company} with score {score}")
    #     file_path = self.output_file_directory / 'job_score.json'

    #     # Get current date and time
    #     current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
    #     # Data format to be saved
    #     job_data = {
    #         "search_term": job.position, 
    #         "company": job.company,
    #         "job_title": job.title,
    #         "link": job.link,
    #         "score": score,  # Adds the score to the record
    #         "timestamp": current_time  # Adds the timestamp
    #     }

    #     # Check if file exists, if not, create a new one
    #     if not file_path.exists():
    #         try:
    #             with open(file_path, 'w') as f:
    #                 json.dump([job_data], f, indent=4)
    #             logger.debug(f"Created new job_score.json with job: {job.title}")
    #         except Exception as e:
    #             logger.error(f"Failed to create job_score.json: {e}", exc_info=True)
    #             raise
    #     else:
    #         # If it exists, load existing data and append the new job
    #         try:
    #             with open(file_path, 'r+') as f:
    #                 try:
    #                     existing_data = json.load(f)
    #                     if not isinstance(existing_data, list):
    #                         logger.warning("job_score.json format is incorrect. Overwriting with a new list.")
    #                         existing_data = []
    #                 except json.JSONDecodeError:
    #                     logger.warning("job_score.json is empty or corrupted. Initializing with an empty list.")
    #                     existing_data = []
                    
    #                 existing_data.append(job_data)
    #                 f.seek(0)
    #                 json.dump(existing_data, f, indent=4)
    #                 f.truncate()
    #             logger.debug(f"Appended job to job_score.json: {job.title}")
    #         except Exception as e:
    #             logger.error(f"Failed to append job to job_score.json: {e}", exc_info=True)
    #             raise
    #     logger.debug(f"Job saved successfully: {job.title} with score {score}")