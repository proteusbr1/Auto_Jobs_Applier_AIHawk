# src/job_manager/job_navigator.py
"""
Handles navigation within a job search website (specifically designed for LinkedIn),
including moving between pages and scrolling job lists.
"""
import time
from loguru import logger
from typing import Optional
from urllib.parse import quote_plus

# Selenium imports
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import WebDriverException, TimeoutException, StaleElementReferenceException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Utils
import src.utils as utils


class JobNavigator:
    """
    Handles navigation tasks for job searching, like changing pages and scrolling.
    Contains logic specific to LinkedIn URL structure and page elements.
    """
    # --- Constants ---
    MAX_NAVIGATION_RETRIES = 3
    MAX_SCROLL_ERRORS = 3
    DEFAULT_WAIT_TIME = 20
    JOBS_PER_PAGE = 25 # LinkedIn standard

    # Locators
    LOADER_LOCATOR = (By.CLASS_NAME, 'artdeco-loader')
    MAIN_CONTAINER_LOCATOR = (By.ID, "main")
    JOB_LIST_ITEM_SELECTOR = 'li.scaffold-layout__list-item[data-occludable-job-id]' # Used for checking page load and scrolling
    NO_RESULTS_BANNER_LOCATOR = (By.CLASS_NAME, 'jobs-search-no-results-banner')
    # --- End Constants & Locators ---


    def __init__(self, driver: WebDriver, wait_time: Optional[int] = None):
        """
        Initializes the JobNavigator.

        Args:
            driver (WebDriver): The Selenium WebDriver instance.
            wait_time (Optional[int]): Default wait time for explicit waits.
                                       Defaults to DEFAULT_WAIT_TIME.
        """
        if not isinstance(driver, WebDriver):
             raise TypeError("driver must be an instance of selenium.webdriver.remote.webdriver.WebDriver")
        self.driver = driver
        self.wait_time = wait_time if wait_time is not None else self.DEFAULT_WAIT_TIME
        self.wait = WebDriverWait(self.driver, self.wait_time)
        logger.debug(f"JobNavigator initialized with wait time: {self.wait_time}s.")


    def construct_search_url(self, base_search_params: str, position: str, search_location_id_or_name: str, page_number: int) -> str:
        """
        Constructs the full LinkedIn job search URL for a specific page.

        Args:
            base_search_params (str): Pre-constructed string of base parameters (filters like remote, exp level, etc.). Starts with '?'.
            position (str): The job position keyword(s).
            search_location_id_or_name (str): The geographic location name or geoId.
            page_number (int): The results page number (0-indexed).

        Returns:
            str: The fully constructed URL.
        """
        start_index = page_number * self.JOBS_PER_PAGE

        # Handle location parameter construction (specific to LinkedIn)
        # Ensure comparison is case-insensitive and handles potential None
        loc_lower = search_location_id_or_name.lower().strip() if search_location_id_or_name else ""

        if loc_lower.isdigit(): # Assume it's a geoId
             location_param = f"&geoId={loc_lower}"
        elif loc_lower == "worldwide":
             location_param = "&geoId=92000000" # LinkedIn's ID for Worldwide
        elif loc_lower: # If it's a non-empty string (location name)
             # Use quote_plus (imported at top)
             location_param = f"&location={quote_plus(search_location_id_or_name)}" # Use original case for encoding
        else: # Handle empty or None location
             logger.warning("Search location name is empty. Location parameter will be omitted.")
             location_param = ""


        # Combine parts, ensure position is also encoded
        url = (
            f"https://www.linkedin.com/jobs/search/{base_search_params}"
            f"&keywords={quote_plus(position)}"
            f"{location_param}" # Add location param if available
            f"&start={start_index}"
        )
        logger.trace(f"Constructed URL for page {page_number}: {url}")
        return url


    def go_to_job_page(self, url: str) -> bool:
        """
        Navigates the browser to the specified job search URL and verifies load state.

        Args:
            url (str): The target URL.

        Returns:
            bool: True if navigation and page load seem successful, False otherwise.
        """
        logger.debug(f"Navigating to URL: {url}")
        try:
            self.driver.get(url)
            # Wait for essential page elements to confirm navigation success
            self.wait.until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, self.JOB_LIST_ITEM_SELECTOR)),
                    EC.presence_of_element_located(self.NO_RESULTS_BANNER_LOCATOR)
                )
            )
            logger.debug(f"Navigation to {url} successful, key elements present.")
            return True
        except TimeoutException:
            logger.warning(f"Timed out waiting for key elements after navigating to {url}. Page might not have loaded correctly.")
            utils.capture_screenshot(self.driver, f"navigate_timeout_{int(time.time())}")
            return False
        except WebDriverException as wd_exc:
            logger.error(f"WebDriverException during navigation to {url}: {wd_exc}", exc_info=True)
            utils.capture_screenshot(self.driver, f"navigate_webdriver_error_{int(time.time())}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during navigation to {url}: {e}", exc_info=True)
            utils.capture_screenshot(self.driver, f"navigate_unexpected_error_{int(time.time())}")
            return False

    def next_job_page(self, position: str, search_location: str, job_page_num: int, base_search_url_params: str) -> Optional[str]:
        """
        Navigates to the next job search results page.

        Args:
            position (str): Job position/keywords.
            search_location (str): Location name or geoId.
            job_page_num (int): The target page number (0-indexed).
            base_search_url_params (str): Base URL parameters string (starts with '?').

        Returns:
            Optional[str]: The URL navigated to if successful, None otherwise.
        """
        target_url = self.construct_search_url(base_search_url_params, position, search_location, job_page_num)
        logger.info(f"Attempting to navigate to page {job_page_num} for '{position}' in '{search_location}'...")

        navigation_successful = False
        for attempt in range(self.MAX_NAVIGATION_RETRIES):
            if self.go_to_job_page(target_url):
                navigation_successful = True
                break
            else:
                logger.warning(f"Navigation attempt {attempt + 1}/{self.MAX_NAVIGATION_RETRIES} failed for page {job_page_num}. Retrying...")
                time.sleep(2 * (attempt + 1)) # Exponential backoff basic

        if not navigation_successful:
            logger.error(f"Failed to navigate to job page {job_page_num} after {self.MAX_NAVIGATION_RETRIES} attempts.")
            return None

        return target_url

    def _check_connection_status(self) -> bool:
        """Checks if essential LinkedIn elements are present, indicating a stable page."""
        logger.trace("Checking page connection status...")
        try:
            # Check for main container
            if not self.driver.find_elements(*self.MAIN_CONTAINER_LOCATOR):
                logger.warning("Main container missing - possible connection issue.")
                return False

            # Check for job list items OR no results banner
            has_job_items = bool(self.driver.find_elements(By.CSS_SELECTOR, self.JOB_LIST_ITEM_SELECTOR))
            has_no_results = bool(self.driver.find_elements(*self.NO_RESULTS_BANNER_LOCATOR))

            if not has_job_items and not has_no_results:
                logger.warning("Neither job items nor 'no results' banner found - possible connection issue.")
                return False

            logger.trace("Page connection status seems OK.")
            return True
        except WebDriverException as e:
            # Handle cases where driver interaction fails (e.g., browser closed)
            logger.warning(f"WebDriverException checking connection status: {e}")
            return False
        except Exception as e:
            logger.warning(f"Unexpected error checking connection status: {e}")
            return False # Assume unstable on error

    def scroll_jobs(self) -> bool:
        """
        Scrolls through the job list to load all job elements using item-by-item scrollIntoView.
        (Reverted logic based on previously working code)

        Returns:
            bool: True if scrolling was successful, False otherwise.
        """
        logger.debug("Starting scroll_jobs (using scrollIntoView strategy)...")

        # Use the class constant selector
        job_item_locator = (By.CSS_SELECTOR, self.JOB_LIST_ITEM_SELECTOR)

        if not self._check_connection_status():
            logger.warning("Initial connection check failed. Attempting scroll anyway, but results may be incomplete.")

        try:
            # Get initial items - retry finding if necessary
            job_items = []
            for _ in range(3): # Retry finding initial items
                try:
                    job_items = self.driver.find_elements(*job_item_locator)
                    if job_items: break
                except StaleElementReferenceException:
                    logger.debug("Stale element finding initial items, retrying...")
                    time.sleep(0.5)
                except Exception as find_err:
                     logger.warning(f"Error finding initial job items: {find_err}")
                     time.sleep(1)
            
            total_jobs = len(job_items)
            logger.debug(f"Found {total_jobs} initial job items.")

            if total_jobs == 0:
                # Check for no results banner again, maybe it appeared late
                if self.driver.find_elements(*self.NO_RESULTS_BANNER_LOCATOR):
                    logger.info("No jobs found (confirmed by no-results banner). No scrolling needed.")
                    return True # No error, just no jobs
                else:
                    logger.warning("No job items found for scrolling. Page may not be loaded properly or selector is wrong.")
                    return False # Indicate potential failure

            idx = 0
            consecutive_errors = 0
            max_consecutive_errors = self.MAX_SCROLL_ERRORS # Use class constant

            last_total_jobs = 0 # To detect if new jobs are loaded

            while idx < total_jobs and consecutive_errors < max_consecutive_errors:
                try:
                    # Re-fetch the job items to avoid stale references and get newly loaded ones
                    current_job_items = self.driver.find_elements(*job_item_locator)
                    current_total_jobs = len(current_job_items)

                    if current_total_jobs > last_total_jobs:
                         logger.debug(f"Job count increased from {last_total_jobs} to {current_total_jobs}")
                         total_jobs = current_total_jobs # Update total if more loaded
                         last_total_jobs = current_total_jobs

                    # Check if we've somehow gone past the end (shouldn't happen often with re-fetch)
                    if idx >= current_total_jobs:
                        logger.debug(f"Index {idx} is out of bounds ({current_total_jobs} items). Ending scroll.")
                        break

                    job_item = current_job_items[idx]

                    # Scroll the specific job item into view
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", job_item)
                    logger.debug(f"Scrolled job item {idx + 1}/{total_jobs} into view.")

                    # Wait briefly for potential loading spinner triggered by the scroll
                    self._wait_for_loader(timeout=2) # Use internal helper, short timeout

                    # Small pause allows content/layout to potentially settle
                    time.sleep(0.1)

                    idx += 1
                    consecutive_errors = 0 # Reset error count on success

                except StaleElementReferenceException:
                    logger.warning(f"StaleElementReferenceException at index {idx}. Re-fetching and retrying scroll.")
                    consecutive_errors += 1
                    time.sleep(0.5) # Wait a bit before retrying the same index
                    # The loop will re-fetch `current_job_items` at the start

                except WebDriverException as wd_e:
                    logger.warning(f"WebDriverException scrolling item {idx+1}: {wd_e}")
                    consecutive_errors += 1
                    idx += 1 # Skip this item on driver error
                    time.sleep(0.5)
                    if "disconnected" in str(wd_e) or "connection refused" in str(wd_e):
                         logger.error("Browser disconnected during scroll.")
                         return False # Critical failure

                except Exception as e:
                    logger.warning(f"Unexpected error scrolling to job item {idx + 1}: {e}", exc_info=True)
                    consecutive_errors += 1
                    idx += 1 # Try the next item on generic error
                    time.sleep(0.5)

                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Max consecutive scroll errors ({max_consecutive_errors}) reached. Stopping scroll.")
                    return False # Indicate failure after too many errors

            logger.debug(f"Scrolling finished. Processed ~{idx} items.")
            return True # Scrolling completed (potentially partially if errors occurred but limit not reached)

        except Exception as e:
            logger.error(f"A critical error occurred during the scroll_jobs setup or loop: {e}", exc_info=True)
            utils.capture_screenshot(self.driver, f"scroll_critical_error_{int(time.time())}")
            return False # Indicate critical failure

    def _wait_for_loader(self, timeout: int = 5) -> bool:
        """Waits for the LinkedIn loading spinner to disappear (short timeout)."""
        logger.trace(f"Waiting up to {timeout}s for loader {self.LOADER_LOCATOR} to disappear...")
        try:
            # Use a shorter wait time specific to this check
            short_wait = WebDriverWait(self.driver, timeout)
            short_wait.until(EC.invisibility_of_element_located(self.LOADER_LOCATOR))
            logger.trace("Loader disappeared or wasn't present.")
            return True
        except TimeoutException:
            logger.trace(f"Loader did not disappear within {timeout}s.")
            return False
        except Exception as e:
             # Catch other errors like NoSuchElement if the loader sometimes doesn't appear at all
             logger.trace(f"Error waiting for loader invisibility (may be harmless): {e}")
             return True # Assume it's okay if the check itself errors