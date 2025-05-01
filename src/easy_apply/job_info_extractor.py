# src/easy_apply/job_info_extractor.py
"""
Extracts detailed job information (Description, Salary, Recruiter) from a
specific job page, typically after navigation. Designed for LinkedIn job pages.
"""
import time
from typing import Optional
from loguru import logger

# Selenium Imports
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException, ElementClickInterceptedException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Utils
import src.utils as utils


class JobInfoExtractor:
    """
    Extracts specific details like description, salary, and recruiter info
    from a loaded job details page (primarily LinkedIn).
    """
    # --- Locators ---
    PREMIUM_URL_FRAGMENT = "linkedin.com/premium"

    # Description
    SEE_MORE_DESC_BUTTON_XPATH_1 = '//button[@aria-label="Click to see more description"]'
    SEE_MORE_DESC_BUTTON_XPATH_2 = '//button[contains(@class, "jobs-description__footer-button")]'
    SEE_MORE_DESC_BUTTON_XPATH_3 = '//button[contains(text(), "See more")]'
    DESCRIPTION_TEXT_SELECTOR_1 = (By.CLASS_NAME, "jobs-description-content__text")
    DESCRIPTION_TEXT_SELECTOR_2 = (By.XPATH, "//div[contains(@class, 'jobs-description-content__text')]") # Redundant? Keep for safety.
    DESCRIPTION_BOX_SELECTOR = (By.XPATH, "//div[contains(@class, 'jobs-box__html-content')]")
    DESCRIPTION_DETAILS_SELECTOR = (By.XPATH, "//div[@id='job-details']")
    DESCRIPTION_ARTICLE_SELECTOR = (By.XPATH, "//div[contains(@class, 'jobs-description')]//article")
    MAIN_CONTENT_SELECTOR = (By.TAG_NAME, "main")

    # Salary
    SALARY_INSIGHT_SELECTOR = (By.XPATH, "//li[contains(@class, 'job-insight') and contains(., '$')]//span[@aria-hidden='true']") # Look for $ sign insight, get actual span
    SALARY_INSIGHT_SELECTOR_ALT = (By.XPATH,"//li[contains(@class, 'job-insight--highlight')]//span[@dir='ltr']") # Original selector

    # Recruiter
    HIRING_TEAM_HEADER_XPATH = '//h2[contains(text(),"Meet the hiring team") or contains(text(),"Job poster")]' # Include "Job poster"
    RECRUITER_LINK_XPATH = './/following::a[contains(@href, "linkedin.com/in/")]' # Find links after header
    # --- End Locators ---

    DEFAULT_WAIT_TIME = 10 # Default wait for this extractor

    def __init__(self, driver: WebDriver, wait_time: Optional[int] = None):
        """
        Initializes the JobInfoExtractor.

        Args:
            driver (WebDriver): The Selenium WebDriver instance.
            wait_time (Optional[int]): Default wait time for waits. Defaults to DEFAULT_WAIT_TIME.
        """
        if not isinstance(driver, WebDriver): raise TypeError("driver must be WebDriver")
        self.driver = driver
        self.wait_time = wait_time if wait_time is not None else self.DEFAULT_WAIT_TIME
        self.wait = WebDriverWait(self.driver, self.wait_time)
        logger.debug("JobInfoExtractor initialized.")

    def check_for_premium_redirect(self, original_job_link: str, max_attempts: int = 3) -> None:
        """
        Checks if redirected to LinkedIn Premium, attempts to navigate back.

        Args:
            original_job_link (str): The intended job page URL.
            max_attempts (int): Max retries to return to the job page.

        Raises:
            RuntimeError: If unable to return to the job page after max attempts.
        """
        logger.debug("Checking for potential Premium page redirect...")
        try:
            current_url = self.driver.current_url
            attempts = 0
            while self.PREMIUM_URL_FRAGMENT in current_url and attempts < max_attempts:
                attempts += 1
                logger.warning(f"Redirected to Premium page. Attempt {attempts}/{max_attempts} to return to: {original_job_link}")
                self.driver.get(original_job_link)
                try:
                    # Wait specifically for the URL to change back, short timeout
                    WebDriverWait(self.driver, 5).until(EC.url_contains(original_job_link.split('?')[0])) # Check base URL
                    logger.debug("Successfully navigated back to job page.")
                    current_url = self.driver.current_url # Update URL after navigation
                except TimeoutException:
                    logger.warning(f"Attempt {attempts}: Timed out waiting to return to job page URL.")
                    current_url = self.driver.current_url # Update URL even on timeout

            if self.PREMIUM_URL_FRAGMENT in current_url:
                error_msg = f"Failed to return to job page from Premium redirect after {max_attempts} attempts. Aborting application for this job."
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            else:
                 logger.debug("Premium redirect check passed (or successfully returned).")

        except WebDriverException as e:
             logger.error(f"WebDriverException during Premium redirect check: {e}", exc_info=True)
             # Re-raise as runtime error? Or allow continuation? Raising for now.
             raise RuntimeError(f"Error checking premium redirect: {e}") from e


    def get_job_description(self) -> str:
        """
        Retrieves the full job description text from the page.

        Attempts to click "See more" and uses multiple selectors for robustness.

        Returns:
            str: The job description, or a placeholder string if not found/error occurs.
        """
        logger.debug("Extracting job description...")
        max_attempts = 2 # Try once, then refresh and try again
        for attempt in range(max_attempts):
             logger.debug(f"Attempt {attempt + 1}/{max_attempts} to get job description.")
             try:
                 # 1. Try clicking "See more"
                 self._click_see_more_description()

                 # 2. Try extracting text using various selectors
                 description_selectors = [
                     self.DESCRIPTION_TEXT_SELECTOR_1, self.DESCRIPTION_TEXT_SELECTOR_2,
                     self.DESCRIPTION_BOX_SELECTOR, self.DESCRIPTION_DETAILS_SELECTOR,
                     self.DESCRIPTION_ARTICLE_SELECTOR
                 ]
                 description = ""
                 for locator in description_selectors:
                     try:
                          # Use presence_of_element_located for potentially hidden elements after click
                          desc_element = WebDriverWait(self.driver, 3).until(EC.presence_of_element_located(locator))
                          # Get text using javascript for potentially complex elements
                          description = self.driver.execute_script("return arguments[0].innerText;", desc_element).strip()
                          if description:
                               logger.debug(f"Found description using {locator}. Length: {len(description)}")
                               return description # Return first non-empty description found
                     except TimeoutException:
                          logger.trace(f"Description selector {locator} timed out.")
                          continue # Try next selector
                     except Exception as e:
                          logger.warning(f"Error extracting text with {locator}: {e}")
                          continue # Try next selector

                 # 3. Fallback: Get text from main content area
                 if not description:
                      logger.warning("Specific description elements not found. Falling back to main content text.")
                      try:
                           main_content = self.driver.find_element(*self.MAIN_CONTENT_SELECTOR)
                           description = main_content.text.strip()
                           if description:
                                logger.info("Retrieved description from main content as fallback.")
                                return description
                      except Exception as main_e:
                           logger.error(f"Could not extract text from main content: {main_e}")

                 # If description still not found after all selectors and fallback
                 logger.warning(f"Could not extract job description on attempt {attempt + 1}.")
                 if attempt < max_attempts - 1:
                      logger.info("Refreshing page and retrying description extraction...")
                      self.driver.refresh()
                      time.sleep(3) # Wait for reload
                      continue # Go to next attempt
                 else:
                      # Last attempt failed
                      logger.error("Failed to retrieve job description after multiple attempts.")
                      utils.capture_screenshot(self.driver, "job_description_failed")
                      return "Job Description Not Found"

             except Exception as e:
                  logger.error(f"Unexpected error getting job description on attempt {attempt + 1}: {e}", exc_info=True)
                  if attempt < max_attempts - 1:
                       try:
                            logger.info("Attempting refresh after unexpected error.")
                            self.driver.refresh()
                            time.sleep(3)
                            continue
                       except Exception as refresh_e:
                            logger.error(f"Failed to refresh after error: {refresh_e}")
                            break # Stop retrying if refresh fails
                  else:
                      utils.capture_screenshot(self.driver, "job_description_unexpected_error")
                      return f"Error Retrieving Job Description: {e}"

        # Should not be reached if loop logic is correct, but return default on failure
        return "Job Description Retrieval Failed"


    def _click_see_more_description(self) -> None:
        """Attempts to click the 'See more' button for the job description."""
        logger.trace("Checking for 'See more' description button...")
        see_more_selectors = [
            self.SEE_MORE_DESC_BUTTON_XPATH_1,
            self.SEE_MORE_DESC_BUTTON_XPATH_2,
            self.SEE_MORE_DESC_BUTTON_XPATH_3
        ]
        for selector in see_more_selectors:
            try:
                # Use a short wait time as the button might not exist
                see_more_button = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                logger.debug(f"Found 'See more' button using selector: {selector}")
                # Scroll into view if needed and click
                self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", see_more_button)
                time.sleep(0.3)
                see_more_button.click()
                logger.debug("Clicked 'See more' description button.")
                time.sleep(0.5) # Wait for content to potentially load
                return # Stop after first successful click
            except TimeoutException:
                logger.trace(f"'See more' button not found or not clickable with selector: {selector}")
                continue
            except ElementClickInterceptedException:
                 logger.warning(f"Click intercepted for 'See more' button ({selector}). Trying JS click.")
                 try:
                      self.driver.execute_script("arguments[0].click();", see_more_button)
                      logger.info("Clicked 'See more' description button using JS.")
                      time.sleep(0.5)
                      return
                 except Exception as js_e:
                      logger.error(f"JS click also failed for 'See more' button: {js_e}")
                      continue # Try next selector if JS click fails
            except Exception as e:
                logger.warning(f"Error clicking 'See more' button with selector {selector}: {e}")
                continue # Try next selector
        logger.debug("'See more' description button not found or could not be clicked.")


    def get_job_salary(self) -> str:
        """
        Retrieves the job salary information, if available in the standard 'insight' section.

        Returns:
            str: The salary text found, or an empty string if not present.
        """
        logger.debug("Extracting job salary information...")
        salary = ""
        try:
             # Try the selector looking for '$' symbol first
             elements = self.driver.find_elements(*self.SALARY_INSIGHT_SELECTOR)
             if elements and elements[0].is_displayed():
                  salary = elements[0].text.strip()
                  if salary:
                       logger.info(f"Found salary info using primary selector: '{salary}'")
                       return salary

             # Fallback to the original selector if the first didn't yield results
             logger.debug("Primary salary selector failed, trying alternative...")
             elements = self.driver.find_elements(*self.SALARY_INSIGHT_SELECTOR_ALT)
             if elements and elements[0].is_displayed():
                  salary = elements[0].text.strip()
                  if salary:
                       logger.info(f"Found salary info using alternative selector: '{salary}'")
                       return salary

             logger.debug("Salary information not found in standard insight sections.")
             return ""
        except NoSuchElementException:
            logger.debug("Salary element not found.")
            return ""
        except Exception as e:
            logger.warning(f"Error extracting job salary: {e}", exc_info=True)
            return ""
