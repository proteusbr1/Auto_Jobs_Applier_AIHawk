"""
Module for handling job navigation in the AIHawk Job Manager.
"""
import time
from loguru import logger
from selenium.common.exceptions import WebDriverException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import src.utils as utils


class JobNavigator:
    """
    Class for handling job navigation in the AIHawk Job Manager.
    """
    def __init__(self, driver, wait_time: int = 20):
        """
        Initialize the JobNavigator class.

        Args:
            driver: The Selenium WebDriver instance.
            wait_time (int, optional): The maximum wait time for WebDriver operations. Defaults to 20.
        """
        self.driver = driver
        self.wait = WebDriverWait(self.driver, wait_time)

    def next_job_page(self, position: str, search_country: str, job_page: int, base_search_url: str):
        """
        Navigates to the specified job page based on the job position and location.
        Includes retry mechanism for handling unstable connections.

        Args:
            position (str): The job position to search for.
            search_country (str): The location/country to search in.
            job_page (int): The page number to navigate to.
            base_search_url (str): The base search URL with query parameters.
            
        Returns:
            str: The URL that was navigated to.
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
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
                    f"https://www.linkedin.com/jobs/search/{base_search_url}"
                    f"&keywords={position}{location_url}&start={start}"
                )

                # Log the navigation details for debugging
                logger.debug(
                    f"Navigating to job page: Position='{position}', "
                    f"Location='{search_country}', Page={job_page}, URL='{url}'."
                )

                # Navigate to the constructed URL
                self.driver.get(url)
                
                # Wait for page to load by checking for common LinkedIn job page elements
                try:
                    # Wait for either job listings or no results banner to appear
                    self.wait.until(
                        EC.any_of(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'li.scaffold-layout__list-item[data-occludable-job-id]')),
                            EC.presence_of_element_located((By.CLASS_NAME, 'jobs-search-no-results-banner'))
                        )
                    )
                    logger.debug("Page loaded successfully with expected elements")
                except TimeoutException:
                    logger.warning(f"Page loaded but expected elements not found, retry {retry_count + 1}/{max_retries}")
                    retry_count += 1
                    continue
                
                return url

            except WebDriverException as wd_exc:
                # Handle Selenium-specific exceptions
                logger.warning(
                    f"Selenium WebDriverException occurred while navigating to page {job_page} "
                    f"for position '{position}' in '{search_country}': {wd_exc}. "
                    f"Retry {retry_count + 1}/{max_retries}"
                )
                utils.capture_screenshot(self.driver, f"webdriver_error_page_{job_page}_{retry_count}")
                retry_count += 1
                time.sleep(2)  # Wait before retrying
                
                if retry_count >= max_retries:
                    logger.error("Maximum retry attempts reached for page navigation", exc_info=True)

            except Exception as exc:
                # Handle any other unexpected exceptions
                logger.warning(
                    f"Unexpected error occurred while navigating to page {job_page} "
                    f"for position '{position}' in '{search_country}': {exc}. "
                    f"Retry {retry_count + 1}/{max_retries}"
                )
                utils.capture_screenshot(self.driver, f"unexpected_error_page_{job_page}_{retry_count}")
                retry_count += 1
                time.sleep(2)  # Wait before retrying
                
                if retry_count >= max_retries:
                    logger.error("Maximum retry attempts reached for page navigation", exc_info=True)
        
        # If all retries fail, return the URL anyway to allow the process to continue
        return (
            f"https://www.linkedin.com/jobs/search/{base_search_url}"
            f"&keywords={position}{location_url}&start={start}"
        )

    def _check_connection_status(self):
        """
        Checks if the LinkedIn connection appears to be stable by looking for key page elements.
        
        Returns:
            bool: True if the connection appears stable, False otherwise
        """
        try:
            # Check for the presence of the main container
            main_elements = self.driver.find_elements(By.ID, "main")
            if not main_elements:
                logger.warning("LinkedIn main container not found - possible connection issue")
                return False
                
            # Check if job list is present
            job_list = self.driver.find_elements(By.CSS_SELECTOR, 'li.scaffold-layout__list-item[data-occludable-job-id]')
            if not job_list:
                # Check if it's a legitimate "no results" page
                no_results = self.driver.find_elements(By.CLASS_NAME, 'jobs-search-no-results-banner')
                if not no_results:
                    logger.warning("Neither job listings nor 'no results' banner found - possible connection issue")
                    return False
            
            return True
        except Exception as e:
            logger.warning(f"Error checking connection status: {e}")
            return False

    def scroll_jobs(self):
        """
        Scrolls through the job list to load all job elements.
        Implements a more resilient approach to handle connection instability.

        Returns:
            bool: True if scrolling was successful, False otherwise.
        """
        logger.debug("Starting scroll_jobs.")

        # Define selectors
        job_item_locator = (By.CSS_SELECTOR, 'li.scaffold-layout__list-item[data-occludable-job-id]')
        
        # First check if the connection is stable
        if not self._check_connection_status():
            logger.warning("Connection appears unstable. Will attempt to scroll but may encounter issues.")
            # We'll continue anyway to attempt partial loading

        try:
            # Get the total number of job items
            job_items = self.driver.find_elements(*job_item_locator)
            total_jobs = len(job_items)
            logger.debug(f"Found {total_jobs} job items.")
            
            if total_jobs == 0:
                logger.warning("No job items found for scrolling. Page may not be loaded properly.")
                return False

            # Use a more resilient scrolling approach
            idx = 0
            consecutive_errors = 0
            max_consecutive_errors = 3
            
            while idx < total_jobs and consecutive_errors < max_consecutive_errors:
                try:
                    # Re-fetch the job items to avoid stale references
                    job_items = self.driver.find_elements(*job_item_locator)
                    
                    # Check if we've reached the end
                    if idx >= len(job_items):
                        logger.debug(f"Reached the end of loaded jobs at index {idx}")
                        break
                        
                    job_item = job_items[idx]

                    # Scroll to the job item
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", job_item)
                    logger.debug(f"Scrolled to job item {idx+1}/{total_jobs}")

                    # Wait for the loader to disappear after scrolling to the item
                    loader_disappeared = self.wait_for_loader()
                    if not loader_disappeared:
                        logger.debug("Loader did not disappear after scrolling to the item. Proceeding.")

                    time.sleep(0.2)  # Wait for the content to load

                    # Increment the index
                    idx += 1
                    consecutive_errors = 0  # Reset error counter on success

                    # Update the total number of job items in case new items are loaded
                    new_total = len(self.driver.find_elements(*job_item_locator))
                    if new_total > total_jobs:
                        logger.debug(f"More jobs loaded. Total increased from {total_jobs} to {new_total}")
                        total_jobs = new_total
                        
                except StaleElementReferenceException as e:
                    logger.warning(f"StaleElementReferenceException at index {idx}: {e}. Re-fetching job items.")
                    consecutive_errors += 1
                    time.sleep(0.5)  # Give a moment for page to stabilize
                    
                    # Try to recover by re-fetching elements
                    try:
                        job_items = self.driver.find_elements(*job_item_locator)
                        total_jobs = len(job_items)
                    except Exception:
                        pass
                        
                except Exception as e:
                    logger.warning(f"Error scrolling to job item {idx+1}: {e}")
                    consecutive_errors += 1
                    idx += 1  # Try the next item
                    time.sleep(0.5)  # Wait before trying again
                    
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(f"Too many consecutive errors ({consecutive_errors}). Stopping scroll.")

            logger.debug(f"Completed scrolling through {idx} job items out of {total_jobs} total.")
            
            # Even partial success is considered success
            return True

        except Exception as e:
            logger.error(f"An error occurred during job scrolling: {e}", exc_info=True)
            # Try a simpler scrolling approach as fallback
            try:
                logger.debug("Attempting simple scroll as fallback")
                # Simple scroll from top to bottom
                self.driver.execute_script("window.scrollTo(0, 0);")  # Start at top
                time.sleep(0.5)
                
                # Scroll down in steps
                height = self.driver.execute_script("return document.body.scrollHeight")
                for i in range(0, height, 300):
                    self.driver.execute_script(f"window.scrollTo(0, {i});")
                    time.sleep(0.2)
                
                logger.debug("Simple scroll completed")
                return True
            except Exception as fallback_error:
                logger.error(f"Fallback scrolling also failed: {fallback_error}")
                return False

    def wait_for_loader(self, timeout=10):
        """
        Waits for the loader element to disappear.

        Args:
            timeout (int, optional): Maximum wait time in seconds. Defaults to 10.

        Returns:
            bool: True if the loader disappeared, False otherwise.
        """
        loader_locator = (By.CLASS_NAME, 'artdeco-loader')
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.invisibility_of_element_located(loader_locator)
            )
            logger.debug("Loader disappeared.")
            return True
        except TimeoutException:
            logger.warning("Loader did not disappear within the specified time.")
            return False
