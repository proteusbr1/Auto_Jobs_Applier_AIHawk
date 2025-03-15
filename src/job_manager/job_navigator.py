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

        Args:
            position (str): The job position to search for.
            search_country (str): The location/country to search in.
            job_page (int): The page number to navigate to.
            base_search_url (str): The base search URL with query parameters.
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

    def scroll_jobs(self):
        """
        Scrolls through the job list to load all job elements.

        Returns:
            bool: True if scrolling was successful, False otherwise.
        """
        logger.debug("Starting scroll_jobs.")

        # Define selectors
        job_item_locator = (By.CSS_SELECTOR, 'li.scaffold-layout__list-item[data-occludable-job-id]')

        try:
            # Get the total number of job items
            total_jobs = len(self.driver.find_elements(*job_item_locator))
            logger.debug(f"Found {total_jobs} job items.")

            idx = 0
            while idx < total_jobs:
                try:
                    # Fetch the job item during each iteration
                    job_items = self.driver.find_elements(*job_item_locator)
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

                    # Update the total number of job items in case new items are loaded
                    total_jobs = len(self.driver.find_elements(*job_item_locator))
                except StaleElementReferenceException as e:
                    logger.warning(f"StaleElementReferenceException at index {idx}: {e}. Re-fetching job items.")
                    # Re-fetch the total job items and continue
                    total_jobs = len(self.driver.find_elements(*job_item_locator))
                except Exception as e:
                    logger.error(f"Error scrolling to job item {idx+1}: {e}", exc_info=True)
                    # Optionally, you can decide to break the loop or continue
                    idx += 1  # Try the next item

            logger.debug("Completed scrolling through all job items.")

            return True

        except Exception as e:
            logger.error(f"An error occurred during job scrolling: {e}", exc_info=True)
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
