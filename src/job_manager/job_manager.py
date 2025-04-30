"""
Main module for the AIHawk Job Manager.
"""
from pathlib import Path

from loguru import logger
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By

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
        self.resume_generator_manager = None  # Initialize to None since we're using direct HTML resume
        
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
        self.description_blacklist = parameters.get("description_blacklist", []) # Get the new description blacklist

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
        
        # Initialize job filter, passing the description blacklist
        self.job_filter = JobFilter(
            title_blacklist=self.title_blacklist,
            company_blacklist=self.company_blacklist,
            description_blacklist=self.description_blacklist, # Pass the description blacklist
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

    def set_resume_generator_manager(self, resume_generator_manager=None):
        """
        Set the resume generator manager for the job manager.

        Args:
            resume_generator_manager: The resume generator manager instance.
                                     Can be None if using direct HTML resume.
        """
        logger.debug("Setting resume generator manager")
        if resume_generator_manager is None:
            logger.debug("Resume generator manager is None - using direct HTML resume")
        self.resume_generator_manager = resume_generator_manager

    def start_applying(self):
        """
        Start the job application process.
        Includes enhanced error handling and connection stability checks.
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
        
        # Define connection issue tracking variables
        consecutive_failures = 0
        max_consecutive_failures = 3
        connection_unstable = False
        recovery_attempts = 0
        max_recovery_attempts = 2
        
        for search in self.searches:
            search_country = search['location']
            search_terms = search['positions']
            
            for search_term in search_terms:
                job_page_number = -1
                logger.debug(f"Starting the search for '{search_term}' in '{search_country}'.")
                consecutive_page_failures = 0
                max_page_failures = 3
        
                while True:  # Loop through job pages
                    try:
                        job_page_number += 1
                        # Navigate to the next job page and get the URL
                        url = self.job_navigator.next_job_page(search_term, search_country, job_page_number, self.base_search_url)
                        logger.info(f"Navigating to job page {job_page_number} for position '{search_term}' in '{search_country}'. URL: {url}")
                        logger.debug("Initiating the application process for this page.")
                        
                        # Check if the page loaded properly
                        if connection_unstable:
                            # If connection was previously unstable, check if it's recovered
                            logger.debug("Checking if connection has stabilized...")
                            import time
                            time.sleep(2)  # Give page time to fully load
                            
                            if not self._is_page_loaded_properly():
                                recovery_attempts += 1
                                if recovery_attempts >= max_recovery_attempts:
                                    logger.error(f"Connection still unstable after {recovery_attempts} recovery attempts. Continuing with limited functionality.")
                                else:
                                    logger.warning(f"Connection still unstable. Recovery attempt {recovery_attempts}/{max_recovery_attempts}. Refreshing page.")
                                    self.driver.refresh()
                                    time.sleep(3)
                                    continue
                            else:
                                logger.info("Connection appears to have stabilized.")
                                connection_unstable = False
                                recovery_attempts = 0
        
                        try:
                            job_elements = self.job_extractor.get_jobs_from_page()
                            if not job_elements:
                                logger.debug("No more jobs found on this page. Exiting loop.")
                                consecutive_page_failures = 0  # Reset counter on success
                                break
                                
                            # Reset failure counters on success
                            consecutive_failures = 0
                            consecutive_page_failures = 0
                            connection_unstable = False
                            
                        except Exception as e:
                            logger.error(f"Failed to retrieve jobs: {e}", exc_info=True)
                            consecutive_failures += 1
                            consecutive_page_failures += 1
                            
                            if consecutive_page_failures >= max_page_failures:
                                logger.warning(f"Too many consecutive failures ({consecutive_page_failures}) on page {job_page_number}. Moving to next search term.")
                                break
                                
                            if consecutive_failures >= max_consecutive_failures:
                                logger.warning("Multiple consecutive failures suggest connection instability. Will attempt recovery.")
                                connection_unstable = True
                                continue
                                
                            # If failures aren't consecutive enough to break, still try to proceed
                            job_elements = []
        
                        # Only proceed with job application if we have job elements to work with
                        if job_elements:
                            try:
                                # Extract job information from job elements
                                job_list = []
                                processed_jobs = 0
                                skipped_jobs = 0
                                
                                for job_element in job_elements:
                                    try:
                                        job_info = self.job_extractor.extract_job_information_from_tile(job_element)
                                        if job_info is None:
                                            logger.debug("Skipping job tile due to extraction failure.")
                                            skipped_jobs += 1
                                            continue
                                        job_list.append(Job(*job_info, search_term=search_term, search_country=search_country))
                                        processed_jobs += 1
                                    except Exception as job_ex:
                                        logger.warning(f"Error extracting individual job info: {job_ex}")
                                        skipped_jobs += 1
                                
                                logger.debug(f"Processed {processed_jobs} jobs, skipped {skipped_jobs} jobs due to extraction failures")
                                
                                if job_list:
                                    # Apply to jobs
                                    self.job_applier.apply_jobs(job_list, self.job_filter)
                                else:
                                    logger.warning("No valid jobs extracted from the page")
                                    if skipped_jobs > 0 and processed_jobs == 0:
                                        # All jobs were skipped - possible connection issue
                                        consecutive_failures += 1
                                        if consecutive_failures >= max_consecutive_failures:
                                            logger.warning("All jobs failed extraction. Possible connection issue.")
                                            connection_unstable = True
                                
                            except Exception as e:
                                logger.error(f"Error during job application: {e}", exc_info=True)
                                consecutive_failures += 1
                                if consecutive_failures >= max_consecutive_failures:
                                    logger.warning("Multiple consecutive failures suggest connection instability.")
                                    connection_unstable = True
                        
                        logger.debug("Completed applying to jobs on this page.")
        
                    except Exception as e:
                        logger.error(f"Unexpected error during job search: {e}", exc_info=True)
                        consecutive_failures += 1
                        consecutive_page_failures += 1
                        
                        if consecutive_page_failures >= max_page_failures:
                            logger.warning(f"Too many consecutive failures ({consecutive_page_failures}) for search term {search_term}. Moving to next search term.")
                            break
                            
                        if consecutive_failures >= max_consecutive_failures:
                            logger.warning("Multiple consecutive failures suggest connection instability.")
                            connection_unstable = True
                            
                        continue
                
                # End of pages for current search term
                logger.info(f"Completed processing all pages for '{search_term}' in '{search_country}'")
                
        logger.info("Job application process complete for all search terms")

    def _is_page_loaded_properly(self):
        """
        Checks if the current LinkedIn page appears to be loaded properly.
        
        Returns:
            bool: True if the page appears to be loaded properly, False otherwise
        """
        try:
            # Check for common elements that should be present on a properly loaded LinkedIn page
            main_element = self.driver.find_elements(By.ID, "main")
            if not main_element:
                logger.debug("Main element not found - page may not be loaded properly")
                return False
                
            # Check for either job list or no results message
            job_elements = self.driver.find_elements(By.CSS_SELECTOR, 'li.scaffold-layout__list-item[data-occludable-job-id]')
            no_results = self.driver.find_elements(By.CLASS_NAME, 'jobs-search-no-results-banner')
            
            if not job_elements and not no_results:
                logger.debug("Neither job elements nor 'no results' banner found - page may not be loaded properly")
                return False
                
            # Check if the page has minimal content
            page_source = self.driver.page_source
            if len(page_source) < 5000:  # Arbitrary threshold for a properly loaded page
                logger.debug(f"Page source is suspiciously small ({len(page_source)} bytes) - page may not be loaded properly")
                return False
                
            return True
        except Exception as e:
            logger.warning(f"Error checking if page is loaded properly: {e}")
            return False

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
