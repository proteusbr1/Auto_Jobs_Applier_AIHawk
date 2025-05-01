# src/job_manager/job_manager.py
"""
Main orchestrator class for the job processing workflow.

Coordinates navigation, extraction, filtering, and application steps.
Requires configuration and dependencies (WebDriver, LLMProcessor, ResumeManager)
to be set via its `configure` and `set_llm_processor` methods.
"""
from pathlib import Path
from typing import Dict, Any, Optional, List

from loguru import logger
# Selenium imports
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By # For page load check

# Internal components
from src.job import Job, JobCache # Assuming these are defined correctly
from src.llm import LLMProcessor # For type hinting
from src.resume_manager import ResumeManager # For type hinting
from .environment_keys import EnvironmentKeys
from .job_navigator import JobNavigator
from .job_extractor import JobExtractor
from .job_filter import JobFilter
from .job_applier import JobApplier
# Import the renamed Easy Apply handler (ensure this file/class exists)
try:
    from src.easy_apply import EasyApplyHandler # Renamed from EasyApplyHandler
except ImportError:
    logger.error("Could not import EasyApplyHandler. Please ensure src/easy_apply_handler.py exists and the class is named correctly.")
    # Define a placeholder if needed, or let it raise error later
    class EasyApplyHandler: pass # Placeholder


class JobManager:
    """
    Orchestrates the automated job search and application process for a specific
    website (designed primarily for LinkedIn).
    """
    DEFAULT_WAIT_TIME = 20 # Default Selenium wait time in seconds

    def __init__(self, driver: WebDriver, wait_time: Optional[int] = None):
        """
        Initializes the JobManager with the WebDriver instance.

        Args:
            driver (WebDriver): The Selenium WebDriver instance.
            wait_time (Optional[int]): The maximum wait time for WebDriver operations.
                                       Defaults to DEFAULT_WAIT_TIME.
        """
        logger.debug("Initializing JobManager...")
        if not isinstance(driver, WebDriver):
             raise TypeError("driver must be an instance of selenium.webdriver.remote.webdriver.WebDriver")

        self.driver: WebDriver = driver
        self.wait_time: int = wait_time if wait_time is not None else self.DEFAULT_WAIT_TIME
        self.wait: WebDriverWait = WebDriverWait(self.driver, self.wait_time)

        # Components initialized immediately
        self.job_navigator: JobNavigator = JobNavigator(driver, self.wait_time)
        self.job_extractor: JobExtractor = JobExtractor(driver, self.wait_time)
        self.env_keys: EnvironmentKeys = EnvironmentKeys() # Reads env vars on init

        # Components and config set later via methods
        self.llm_processor: Optional[LLMProcessor] = None
        self.resume_manager: Optional[ResumeManager] = None
        self.parameters: Optional[Dict[str, Any]] = None
        self.job_filter: Optional[JobFilter] = None
        self.job_applier: Optional[JobApplier] = None
        self.cache: Optional[JobCache] = None
        self.output_file_directory: Optional[Path] = None

        # Runtime state
        # self.set_old_answers = set() # Is this still needed? Appears unused elsewhere. Remove if so.
        # self.seen_jobs = [] # Replaced by JobCache logic

        logger.debug("JobManager initialized successfully.")

    # --- Configuration Methods ---

    def set_llm_processor(self, llm_processor: LLMProcessor):
        """Sets the LLM Processor instance."""
        if not isinstance(llm_processor, LLMProcessor):
             raise TypeError("llm_processor must be an instance of LLMProcessor")
        self.llm_processor = llm_processor
        logger.info("LLM Processor set for JobManager.")
        # Note: LLM Processor is passed to EasyApplyHandler during start_processing

    def configure(self, parameters: Dict[str, Any], resume_manager: ResumeManager):
        """
        Configures the JobManager with application parameters, resume manager,
        and initializes dependent components like Cache and Filter.

        Args:
            parameters (Dict[str, Any]): Validated configuration parameters.
            resume_manager (ResumeManager): Initialized resume manager instance.
        """
        logger.info("Configuring JobManager...")
        if not isinstance(parameters, dict): raise TypeError("parameters must be a dict")
        if not isinstance(resume_manager, ResumeManager): raise TypeError("resume_manager must be an instance of ResumeManager")

        self.parameters = parameters
        self.resume_manager = resume_manager

        # Extract specific parameters needed by JobManager or its components
        self.output_file_directory = parameters.get("outputFileDirectory")
        if not self.output_file_directory or not isinstance(self.output_file_directory, Path):
             raise ValueError("Configuration parameters missing valid 'outputFileDirectory'.")

        # Initialize Cache
        try:
             self.cache = JobCache(self.output_file_directory)
             logger.info(f"JobCache initialized for directory: {self.output_file_directory}")
        except Exception as e:
             logger.error(f"Failed to initialize JobCache: {e}", exc_info=True)
             raise RuntimeError(f"Failed to initialize JobCache: {e}") from e


        # Initialize Filter (pass description blacklist)
        self.job_filter = JobFilter(
            title_blacklist=parameters.get("title_blacklist", []),
            company_blacklist=parameters.get("company_blacklist", []),
            description_blacklist=parameters.get("description_blacklist", []),
            cache=self.cache
        )
        logger.info("JobFilter initialized.")

        # Extract other parameters if needed directly by JobManager
        # self.apply_once_at_company = parameters.get("apply_once_at_company", False)
        # self.min_applicants = parameters.get("job_applicants_threshold", {}).get("min_applicants", 0)
        # self.max_applicants = parameters.get("job_applicants_threshold", {}).get("max_applicants", float("inf"))

        logger.info("JobManager configured successfully.")


    # --- Main Execution Method ---

    def start_processing(self):
        """
        Starts the main job processing workflow: searching, navigating pages,
        extracting jobs, filtering, and initiating applications.
        """
        logger.info("Starting main job processing workflow...")

        # --- Validate Prerequisites ---
        if not self.llm_processor:
            raise RuntimeError("LLM Processor has not been set. Call set_llm_processor() first.")
        if not self.parameters or not self.resume_manager or not self.job_filter or not self.cache:
            raise RuntimeError("JobManager has not been configured. Call configure() first.")
        if not EasyApplyHandler: # Check if placeholder is still used
             raise RuntimeError("EasyApplyHandler component is not available (Import Error?). Cannot proceed.")

        # --- Initialize Application Handler ---
        # Pass necessary dependencies: driver, resume_manager, llm_processor, cache
        try:
            # Assuming EasyApplyHandler needs these specific dependencies
            application_handler = EasyApplyHandler(
                driver=self.driver,
                resume_manager=self.resume_manager,
                # old_answers_set=self.set_old_answers, # Pass if needed, else remove
                llm_processor=self.llm_processor,
                cache=self.cache,
            )
            self.job_applier = JobApplier(application_handler, self.cache)
            logger.info("JobApplier and EasyApplyHandler initialized.")
        except Exception as e:
             logger.error(f"Failed to initialize EasyApplyHandler or JobApplier: {e}", exc_info=True)
             raise RuntimeError(f"Failed to initialize application components: {e}") from e

        # --- Get Base Search URL Parameters ---
        try:
             base_search_url_params = self._construct_base_search_url_params(self.parameters)
        except Exception as e:
             logger.error(f"Failed to construct base search URL parameters: {e}", exc_info=True)
             # Decide if fatal or continue with default? Raising for now.
             raise ValueError(f"Invalid parameters for constructing search URL: {e}") from e


        # --- Main Loop ---
        searches = self.parameters.get("searches", [])
        if not searches:
             logger.warning("No searches defined in configuration. Job processing will not run.")
             return

        total_applied_count = 0
        for search_index, search in enumerate(searches):
            search_location = search.get('location', 'UNKNOWN_LOCATION')
            search_terms = search.get('positions', [])
            logger.info(f"--- Starting Search {search_index + 1}/{len(searches)}: Location='{search_location}', Terms={search_terms} ---")

            if not search_terms:
                 logger.warning(f"No position terms found for search in {search_location}. Skipping this search.")
                 continue

            for term_index, search_term in enumerate(search_terms):
                logger.info(f"--- Processing Term {term_index + 1}/{len(search_terms)}: '{search_term}' ---")
                page_number = -1 # Start from page 0
                consecutive_page_failures = 0
                MAX_PAGE_FAILURES = 3 # Max failures for a single search term before moving on

                while True: # Loop through pages for this term
                    page_number += 1
                    logger.debug(f"Processing page {page_number} for term '{search_term}'...")

                    # Navigate to the next page
                    nav_url = self.job_navigator.next_job_page(
                        search_term, search_location, page_number, base_search_url_params
                    )
                    if not nav_url:
                         logger.error(f"Failed to navigate to page {page_number} for '{search_term}'. Skipping rest of term.")
                         break # Break from page loop, move to next term

                    # Extract job elements from the page
                    try:
                        job_elements = self.job_extractor.get_jobs_from_page()
                        if not job_elements:
                            # Could be end of results or an error loading elements
                            logger.info(f"No more job elements found on page {page_number} for '{search_term}'. Moving to next term or search.")
                            break # Break from page loop

                        logger.debug(f"Extracted {len(job_elements)} job tiles from page {page_number}.")
                        consecutive_page_failures = 0 # Reset failure counter on success
                    except Exception as e:
                         logger.error(f"Failed to extract jobs from page {page_number} for '{search_term}': {e}", exc_info=True)
                         consecutive_page_failures += 1
                         if consecutive_page_failures >= MAX_PAGE_FAILURES:
                              logger.error(f"Max page extraction failures ({MAX_PAGE_FAILURES}) reached for '{search_term}'. Skipping rest of term.")
                              break # Break from page loop
                         else:
                              logger.warning(f"Continuing to next page attempt after extraction failure (attempt {consecutive_page_failures}).")
                              continue # Try next page number


                    # Extract detailed job info from elements
                    job_list: List[Job] = []
                    processed_count = 0
                    skipped_extraction_count = 0
                    for element in job_elements:
                         job_data_tuple = self.job_extractor.extract_job_information_from_tile(element)
                         if job_data_tuple:
                              try:
                                   # Unpack tuple matching the EXTRACTOR'S return signature
                                   j_title, j_company, j_location, j_link, j_apply, j_state = job_data_tuple
                                   # Create Job object - description will be added later by EasyApplyHandler
                                   job = Job(
                                        title=j_title,
                                        company=j_company,
                                        location=j_location,
                                        link=j_link,
                                        apply_method=j_apply,
                                        state=j_state,
                                        # description remains default "" or None here
                                        search_term=search_term,
                                        search_country=search_location
                                   )
                                   job_list.append(job)
                                   processed_count += 1
                              except ValueError as unpack_err:
                                   logger.error(f"Error unpacking job data tuple: {unpack_err}. Data: {job_data_tuple}")
                                   skipped_extraction_count += 1
                              except Exception as job_init_e:
                                   logger.warning(f"Failed to initialize Job object from extracted data: {job_init_e}. Data: {job_data_tuple}")
                                   skipped_extraction_count += 1
                         else:
                              skipped_extraction_count += 1

                    logger.info(f"Successfully extracted details for {processed_count} jobs (skipped {skipped_extraction_count} tiles) on page {page_number}.")

                    # Apply to the extracted & valid jobs
                    if job_list:
                        try:
                             applied_on_page = self.job_applier.apply_jobs(job_list, self.job_filter)
                             total_applied_count += len(applied_on_page)
                        except Exception as apply_e:
                             logger.error(f"Error occurred during application process on page {page_number}: {apply_e}", exc_info=True)
                             # Decide how to handle: continue to next page, stop term, stop all? Continuing for now.
                    else:
                         logger.info(f"No valid jobs to apply to on page {page_number} after extraction.")


                    # Optional: Add delay between pages?
                    # import time
                    # time.sleep(random.uniform(1, 3))

                # End of page loop for the current search term
                logger.info(f"Finished processing pages for term '{search_term}'.")

            # End of term loop for the current search
            logger.info(f"Finished processing all terms for location '{search_location}'.")

        # End of search loop
        logger.success(f"Job processing workflow completed. Total application attempts initiated: {total_applied_count}")


    # --- Helper Methods ---

    def _construct_base_search_url_params(self, parameters: Dict[str, Any]) -> str:
        """Constructs the base parameter string for LinkedIn job search URLs."""
        logger.debug("Constructing base search URL parameters from config...")
        url_parts = []

        # Remote filter (f_CF=f_WRA)
        if parameters.get('remote', False):
            url_parts.append("f_CF=f_WRA")

        # Experience Level filter (f_E=...) - LinkedIn uses 1-based index
        # Mapping might be needed if keys don't match LinkedIn IDs exactly
        exp_level_mapping = {'internship': 1, 'entry': 2, 'associate': 3, 'mid-senior level': 4, 'director': 5, 'executive': 6}
        selected_levels = []
        for level_key, enabled in parameters.get('experienceLevel', {}).items():
            if enabled and level_key in exp_level_mapping:
                selected_levels.append(str(exp_level_mapping[level_key]))
        if selected_levels:
            url_parts.append(f"f_E={','.join(selected_levels)}")

        # Distance filter (distance=...)
        distance = parameters.get('distance', 0) # Default distance
        url_parts.append(f"distance={distance}")

        # Job Type filter (f_JT=...) - LinkedIn uses single uppercase letters
        job_type_mapping = {'full-time': 'F', 'contract': 'C', 'part-time': 'P', 'temporary': 'T', 'internship': 'I', 'other': 'O', 'volunteer': 'V'}
        selected_types = []
        for type_key, enabled in parameters.get('jobTypes', {}).items():
             if enabled and type_key in job_type_mapping:
                  selected_types.append(job_type_mapping[type_key])
        if selected_types:
            url_parts.append(f"f_JT={','.join(selected_types)}")

        # Date Posted filter (f_TPR=...) - Use specific values
        date_mapping = {
            "all time": "", # No parameter needed for all time
            "month": "r2592000", # Seconds in 30 days
            "week": "r604800", # Seconds in 7 days
            "24 hours": "r86400" # Seconds in 1 day
        }
        date_param_value = ""
        for date_key, enabled in parameters.get('date', {}).items():
             if enabled and date_key in date_mapping:
                  date_param_value = date_mapping[date_key]
                  break # Assume only one date filter can be active
        if date_param_value:
             url_parts.append(f"f_TPR={date_param_value}")

        # Easy Apply filter (f_AL=true)
        url_parts.append("f_LF=f_AL")

        # Combine parts starting with '?'
        base_url = f"?{'&'.join(filter(None, url_parts))}" # Filter removes empty strings if no date selected, etc.
        logger.debug(f"Constructed base search URL parameters: {base_url}")
        return base_url


    def _is_page_loaded_properly(self) -> bool:
        """
        Checks if the current page appears to be loaded properly with key elements.
        (Helper for error recovery, potentially redundant if navigator handles it).
        """
        logger.trace("Checking if page loaded properly...")
        try:
            # Check for common elements
            if not self.driver.find_elements(By.ID, "main"): return False
            has_jobs = bool(self.driver.find_elements(By.CSS_SELECTOR, 'li.scaffold-layout__list-item[data-occludable-job-id]'))
            has_no_results = bool(self.driver.find_elements(By.CLASS_NAME, 'jobs-search-no-results-banner'))
            if not has_jobs and not has_no_results: return False
            # Basic source length check
            if len(self.driver.page_source) < 5000: return False
            return True
        except WebDriverException as e:
             logger.warning(f"WebDriverException checking page load: {e}")
             return False
        except Exception as e:
            logger.warning(f"Error checking if page loaded: {e}")
            return False