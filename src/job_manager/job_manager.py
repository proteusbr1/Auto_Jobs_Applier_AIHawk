"""
Main module for the AIHawk Job Manager.
"""
from itertools import product
from pathlib import Path
import time
import sys

from loguru import logger
from selenium.webdriver.support.ui import WebDriverWait

from app_config import USE_JOB_SCORE
from src.job import Job, JobCache
from src.job_manager.environment_keys import EnvironmentKeys
from src.job_manager.job_navigator import JobNavigator
from src.job_manager.job_extractor import JobExtractor
from src.job_manager.job_filter import JobFilter
from src.job_manager.job_applier import JobApplier


class AIHawkJobManager:
    """
    Main class for managing job applications on LinkedIn.
    """
    def __init__(self, driver, wait_time: int = 20):
        """
        Initialize the AIHawkJobManager class.

        Args:
            driver: The Selenium WebDriver instance.
            wait_time (int, optional): The maximum wait time for WebDriver operations. Defaults to 20.
        """
        logger.debug("Initializing AIHawkJobManager")
        self.driver = driver
        self.wait = WebDriverWait(self.driver, wait_time)
        self.set_old_answers = set()
        self.easy_applier_component = None
        self.seen_jobs = []
        self.title_blacklist_set = set()
        self.company_blacklist_set = set()
        
        # Initialize components
        self.job_navigator = JobNavigator(driver, wait_time)
        self.job_extractor = JobExtractor(driver, wait_time)
        logger.debug("AIHawkJobManager initialized successfully")

    def set_parameters(self, parameters, resume_manager):
        """
        Set the parameters for the job manager.

        Args:
            parameters (dict): The parameters for the job manager.
            resume_manager: The resume manager instance.
        """
        logger.debug("Setting parameters for AIHawkJobManager")
        self.company_blacklist = parameters.get("company_blacklist", [])
        self.title_blacklist = parameters.get("title_blacklist", [])
        
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
        
        # Initialize job filter
        self.job_filter = JobFilter(
            title_blacklist=self.title_blacklist,
            company_blacklist=self.company_blacklist,
            cache=self.cache
        )
        
        logger.debug("Parameters set successfully")

    def set_gpt_answerer(self, gpt_answerer):
        """
        Set the GPT answerer for the job manager.

        Args:
            gpt_answerer: The GPT answerer instance.
        """
        logger.debug("Setting GPT answerer")
        self.gpt_answerer = gpt_answerer

    def set_resume_generator_manager(self, resume_generator_manager):
        """
        Set the resume generator manager for the job manager.

        Args:
            resume_generator_manager: The resume generator manager instance.
        """
        logger.debug("Setting resume generator manager")
        self.resume_generator_manager = resume_generator_manager

    def start_applying(self):
        """
        Start the job application process.
        """
        logger.debug("Starting job application process")
        from src.aihawk_easy_applier import AIHawkEasyApplier
        self.easy_applier_component = AIHawkEasyApplier(
            self.driver,
            self.resume_manager,
            self.set_old_answers,
            self.gpt_answerer,
            self.resume_generator_manager,
            cache=self.cache,
        )
        
        # Initialize job applier
        self.job_applier = JobApplier(self.easy_applier_component, self.cache)
        
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
                        self.job_navigator.next_job_page(search_term, search_country, job_page_number, self.base_search_url)
                        logger.debug("Initiating the application process for this page.")
        
                        try:
                            job_elements = self.job_extractor.get_jobs_from_page()
                            if not job_elements:
                                logger.debug("No more jobs found on this page. Exiting loop.")
                                break
                        except Exception as e:
                            logger.error("Failed to retrieve jobs.", exc_info=True)
                            break
        
                        try:
                            # Extract job information from job elements
                            job_list = []
                            for job_element in job_elements:
                                job_info = self.job_extractor.extract_job_information_from_tile(job_element)
                                if job_info is None:
                                    logger.debug("Skipping job tile due to extraction failure.")
                                    continue
                                job_list.append(Job(*job_info, search_term=search_term, search_country=search_country))
                            
                            # Apply to jobs
                            self.job_applier.apply_jobs(job_list, self.job_filter)
                        except Exception as e:
                            logger.error(f"Error during job application: {e}", exc_info=True)
                            continue
        
                        logger.debug("Completed applying to jobs on this page.")
        
                except Exception as e:
                    logger.error("Unexpected error during job search.", exc_info=True)
                    continue

    def get_base_search_url(self, parameters):
        """
        Construct the base search URL from parameters.

        Args:
            parameters (dict): The parameters for the job manager.

        Returns:
            str: The base search URL.
        """
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
