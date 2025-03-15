"""
Module for extracting job information in the AIHawk Job Manager.
"""
from loguru import logger
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import src.utils as utils


class JobExtractor:
    """
    Class for extracting job information in the AIHawk Job Manager.
    """
    def __init__(self, driver, wait_time: int = 20):
        """
        Initialize the JobExtractor class.

        Args:
            driver: The Selenium WebDriver instance.
            wait_time (int, optional): The maximum wait time for WebDriver operations. Defaults to 20.
        """
        self.driver = driver
        self.wait = WebDriverWait(self.driver, wait_time)

    def get_jobs_from_page(self):
        """
        Fetches job elements from the current page.

        Returns:
            list: A list of job elements if found, otherwise an empty list.
        """
        logger.debug("Starting get_jobs_from_page.")

        # Define locators at the beginning of the function
        NO_RESULTS_LOCATOR = (By.CLASS_NAME, 'jobs-search-no-results-banner')
        JOB_LIST_CONTAINER_LOCATOR = (By.XPATH, "//main[@id='main']//div[contains(@class, 'scaffold-layout__list-detail-inner')]//ul")
        JOB_TILE_LOCATOR = (By.CSS_SELECTOR, 'li.scaffold-layout__list-item[data-occludable-job-id]')

        try:
            logger.debug(f"Waiting for either {NO_RESULTS_LOCATOR} or job tiles to be present.")

            # Wait until either the 'no results' banner or job elements are present
            self.wait.until(
                EC.any_of(
                    EC.presence_of_element_located(NO_RESULTS_LOCATOR),
                    EC.presence_of_element_located(JOB_TILE_LOCATOR)
                )
            )
            logger.debug("Elements condition met.")

        except TimeoutException:
            logger.warning("Timed out waiting for the 'no results' banner or the job elements.")
            utils.capture_screenshot(self.driver, "job_elements_timeout")
            # logger.debug(f"HTML of the page: {self.driver.page_source}")
            return []

        # Check if the "no results" banner is present
        no_results_elements = self.driver.find_elements(*NO_RESULTS_LOCATOR)
        if no_results_elements:
            no_results_banner = no_results_elements[0]
            banner_text = no_results_banner.text.lower()
            logger.debug(f"No results banner text: '{banner_text}'.")
            if 'no matching jobs found' in banner_text or "unfortunately, things aren't" in banner_text:
                logger.debug("No matching jobs found on this search.")
                return []

        # Proceed to fetch job elements
        try:
            logger.debug("Waiting for job list container to be present.")
            job_list_container = self.wait.until(
                EC.presence_of_element_located(JOB_LIST_CONTAINER_LOCATOR)
            )
            logger.debug("Job list container found.")


        except (TimeoutException, NoSuchElementException) as e:
            logger.warning(f"Exception while waiting for the job list container: {e}")
            return []

        # Scroll to load all job elements
        logger.debug("Initiating optimized scroll to load all job elements.")
        from src.job_manager.job_navigator import JobNavigator
        job_navigator = JobNavigator(self.driver, wait_time=self.wait._timeout)
        job_navigator.scroll_jobs()
        logger.debug("Scrolling completed.")

        try:
            job_list_elements = job_list_container.find_elements(*JOB_TILE_LOCATOR)
            logger.debug(f"Found {len(job_list_elements)} job elements on the page.")

            if not job_list_elements:
                logger.warning("No job elements found on the page.")
                return []

            return job_list_elements

        except StaleElementReferenceException:
            logger.error("StaleElementReferenceException encountered. Attempting to recapture job elements.")
        try:
            logger.debug("Waiting for job list container to be present.")
            job_list_container = self.wait.until(
                EC.presence_of_element_located(JOB_LIST_CONTAINER_LOCATOR)
            )
            logger.debug("Job list container found.")
        except (TimeoutException, NoSuchElementException) as e:
            logger.warning(f"Exception while waiting for the job list container: {e}. Retrying after a short delay.")
            import time
            time.sleep(2)
            try:
                job_list_container = self.driver.find_element(By.XPATH, "//div[contains(@class, 'scaffold-layout__list-detail-inner')]/div[contains(@class, 'scaffold-layout__list')]/ul")
                logger.debug("Fallback: Job list container found using driver.find_element with XPath.")
            except Exception as ex:
                logger.error(f"Fallback failed while retrieving job list container: {ex}", exc_info=True)
                return []
        except Exception as e:
            logger.error(f"Unexpected error while fetching job elements: {e}", exc_info=True)
            return []

    def extract_job_information_from_tile(self, job_tile):
        """
        Extracts job information from a job tile element.

        Args:
            job_tile (WebElement): The Selenium WebElement representing the job tile.

        Returns:
            Tuple[str, str, str, str, str, str]: A tuple containing job_title, company, job_location, link, apply_method, job_state.
        """
        logger.debug("Starting extraction of job information from tile.")

        try:
            job_title = self._extract_job_title(job_tile)
            company = self._extract_company(job_tile)
            link = self._extract_link(job_tile)
            job_location = self._extract_job_location(job_tile)
            apply_method = self._extract_apply_method(job_tile)
            job_state = self._extract_job_state(job_tile)
            return job_title, company, job_location, link, apply_method, job_state
        except Exception as e:
            logger.error(f"Failed to extract job information: {e}", exc_info=True)
            return None  # or you can skip this job tile

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
            job_title_element = job_tile.find_element(By.XPATH, './/a[contains(@class, "job-card-list__title--link")]')
            job_title = job_title_element.text.strip()
            logger.debug(f"Extracted Job Title: '{job_title}'")
        except NoSuchElementException:
            logger.error("Job title element not found.")
            logger.debug(f"Job tile HTML: {job_tile.get_attribute('outerHTML')}")
            utils.capture_screenshot(self.driver, "job_title_error")
        except Exception as e:
            logger.error(f"Unexpected error in _extract_job_title: {e}", exc_info=True)
            logger.debug(f"Job tile HTML: {job_tile.get_attribute('outerHTML')}")
            utils.capture_screenshot(self.driver, "job_title_error")
        return job_title

    def _extract_company(self, job_tile):
        """
        Extracts the company name from the job tile.

        Args:
            job_tile (WebElement): The Selenium WebElement representing the job tile.

        Returns:
            str: The company name.
        """
        logger.debug("Extracting company name from job tile.")  
        company = ""
        try:
            # Try multiple selectors to find the company name
            try:
                subtitle_element = job_tile.find_element(By.CSS_SELECTOR, 'div.artdeco-entity-lockup__subtitle')
                company_location_text = subtitle_element.text.strip()
                if '·' in company_location_text:
                    company = company_location_text.split('·')[0].strip()
                else:
                    company = company_location_text.strip()
            except NoSuchElementException:
                # Try alternative selector
                try:
                    company_element = job_tile.find_element(By.CSS_SELECTOR, 'span.job-card-container__primary-description')
                    company = company_element.text.strip()
                except NoSuchElementException:
                    # Try another alternative selector
                    try:
                        company_element = job_tile.find_element(By.XPATH, ".//a[contains(@class, 'job-card-container__company-name') or contains(@class, 'job-card-list__company-name')]")
                        company = company_element.text.strip()
                    except NoSuchElementException:
                        # One more attempt with a very general selector
                        company_elements = job_tile.find_elements(By.XPATH, ".//span[contains(text(), 'at ')]")
                        if company_elements:
                            company_text = company_elements[0].text
                            if 'at ' in company_text:
                                company = company_text.split('at ')[1].strip()
            
            logger.debug(f"Extracted Company: '{company}'")
        except Exception as e:
            logger.error(f"Unexpected error while extracting company: {e}", exc_info=True)
            logger.debug(f"Job tile HTML: {job_tile.get_attribute('outerHTML')}")
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
            # Use a more robust selector to find the job link, matching any anchor with '/jobs/view/' in its href
            job_title_element = job_tile.find_element(By.CSS_SELECTOR, "a[href*='/jobs/view/']")
            link_attr = job_title_element.get_attribute('href') or job_title_element.get_property('href') or ""
            link = link_attr.split('?')[0] if link_attr else ""
            logger.debug(f"Extracted Link: '{link}'")
        except NoSuchElementException:
            logger.error("Job link element not found using selector a[href*='/jobs/view/'].")
            logger.debug(f"Job tile HTML: {job_tile.get_attribute('outerHTML')}")
        except Exception as e:
            logger.error(f"Unexpected error while extracting job link: {e}", exc_info=True)
            logger.debug(f"Job tile HTML: {job_tile.get_attribute('outerHTML')}")
        return link

    def _extract_job_location(self, job_tile):
        """
        Extracts the job location from the job tile.

        Args:
            job_tile (WebElement): The Selenium WebElement representing the job tile.

        Returns:
            str: The job location.
        """
        logger.debug("Extracting job location from job tile.")
        job_location = ""
        try:
            subtitle_element = job_tile.find_element(By.CSS_SELECTOR, 'div.artdeco-entity-lockup__subtitle')
            company_location_text = subtitle_element.text.strip()
            if '·' in company_location_text:
                job_location = company_location_text.split('·')[1].strip()
            else:
                job_location = company_location_text.strip()
            logger.debug(f"Extracted Job Location: '{job_location}'")
        except NoSuchElementException:
            logger.error("Job location element not found.")
            logger.debug(f"Job tile HTML: {job_tile.get_attribute('outerHTML')}")
        except Exception as e:
            logger.error(f"Unexpected error while extracting job location: {e}", exc_info=True)
            logger.debug(f"Job tile HTML: {job_tile.get_attribute('outerHTML')}")
        return job_location

    def _extract_apply_method(self, job_tile):
        """
        Extracts the apply method from the job_tile.
        Tries multiple selectors to find the 'Easy Apply' button or text.

        Args:
            job_tile (WebElement): The Selenium WebElement representing the job_tile.

        Returns:
            str: The apply method or None if it is not 'Easy Apply' or if the element is not found.
        """
        logger.debug("Starting apply method extraction.")
        apply_method = None
        try:
            # Try multiple selectors to find the Easy Apply button or text
            selectors = [
                # Original selectors
                (By.CSS_SELECTOR, 'button.jobs-apply-button'),
                (By.CSS_SELECTOR, 'li.job-card-container__apply-method'),
                # New selectors
                (By.XPATH, ".//button[contains(text(), 'Easy Apply')]"),
                (By.XPATH, ".//span[contains(text(), 'Easy Apply')]"),
                (By.XPATH, ".//div[contains(@class, 'job-card-container__apply-method') or contains(@class, 'jobs-apply-button')]"),
                # Very general selector
                (By.XPATH, ".//*[contains(text(), 'Easy Apply')]")
            ]
            
            for selector_type, selector in selectors:
                try:
                    element = job_tile.find_element(selector_type, selector)
                    element_text = (element.text or element.get_attribute("innerText") or "").strip().lower()
                    logger.debug(f"Found element with text: '{element_text}' using selector: {selector}")
                    
                    if 'easy apply' in element_text:
                        apply_method = 'Easy Apply'
                        logger.debug("Apply method is 'Easy Apply'.")
                        break
                except NoSuchElementException:
                    continue
                except Exception as e:
                    logger.debug(f"Error with selector {selector}: {e}")
                    continue
            
            # If we still don't have an apply method, check the entire job tile text
            if apply_method is None:
                job_tile_text = job_tile.text.lower()
                if 'easy apply' in job_tile_text:
                    apply_method = 'Easy Apply'
                    logger.debug("Found 'Easy Apply' in job tile text.")
            
        except Exception as e:
            logger.debug(f"Unexpected error while extracting apply method: {e}", exc_info=True)
        
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
            job_state_element = job_tile.find_element(By.CSS_SELECTOR, 'li.job-card-container__footer-job-state')
            job_state = job_state_element.text.strip()
            logger.debug(f"Extracted job state: '{job_state}'")
        except NoSuchElementException:
            logger.debug("Job state element not found.")
        except Exception as e:
            logger.debug(f"Unexpected error while extracting job state: {e}", exc_info=True)
        return job_state
