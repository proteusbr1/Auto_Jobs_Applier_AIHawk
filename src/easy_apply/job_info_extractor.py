"""
Module for extracting job information from LinkedIn job pages.
"""
import time
from typing import Optional
from loguru import logger
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import src.utils as utils

class JobInfoExtractor:
    """
    Extracts job information from LinkedIn job pages.
    """
    
    def __init__(self, driver: WebDriver, wait_time: int = 10):
        """
        Initialize the JobInfoExtractor with a WebDriver instance.
        
        Args:
            driver (WebDriver): The Selenium WebDriver instance.
            wait_time (int): The maximum time to wait for elements to appear.
        """
        self.driver = driver
        self.wait = WebDriverWait(self.driver, wait_time)
    
    def check_for_premium_redirect(self, job_link: str, max_attempts: int = 3) -> None:
        """
        Check if the browser is redirected to the LinkedIn Premium page and attempt to navigate back.

        Args:
            job_link (str): The job link to return to if redirected.
            max_attempts (int): Maximum number of attempts to return to the job page.
        
        Raises:
            Exception: If unable to return to the job page after max_attempts.
        """
        current_url = self.driver.current_url
        attempts = 0

        while "linkedin.com/premium" in current_url and attempts < max_attempts:
            logger.warning(
                "Redirected to LinkedIn Premium page. Attempting to return to job page."
            )
            attempts += 1

            self.driver.get(job_link)
            try:
                self.wait.until(EC.url_to_be(job_link))
                logger.debug(f"Returned to job page: {job_link}")
            except TimeoutException:
                logger.warning(
                    f"Attempt {attempts}: Timed out waiting to return to job page: {job_link}"
                )
            current_url = self.driver.current_url

        if "linkedin.com/premium" in current_url:
            logger.error(
                f"Failed to return to job page after {max_attempts} attempts. Cannot apply for the job."
            )
            raise Exception(
                f"Redirected to LinkedIn Premium page and failed to return after {max_attempts} attempts. Job application aborted."
            )
    
    def get_job_description(self) -> str:
        """
        Retrieves the job description from the job page.
        Handles different LinkedIn job page layouts and potential timing issues.

        Returns:
            str: The job description text.
        """
        logger.debug("Getting job description")
        max_attempts = 3
        attempt = 0
        
        while attempt < max_attempts:
            attempt += 1
            logger.debug(f"Attempt {attempt}/{max_attempts} to get job description")
            
            try:
                # Try to expand the description by clicking "See more" button if it exists
                try:
                    # Multiple selectors for the "See more" button to handle different LinkedIn layouts
                    see_more_selectors = [
                        (By.XPATH, '//button[@aria-label="Click to see more description"]'),
                        (By.XPATH, '//button[contains(@class, "jobs-description__footer-button")]'),
                        (By.XPATH, '//button[contains(text(), "See more")]')
                    ]
                    
                    for selector_type, selector in see_more_selectors:
                        try:
                            see_more_buttons = self.driver.find_elements(selector_type, selector)
                            if see_more_buttons:
                                see_more_button = see_more_buttons[0]
                                if see_more_button.is_displayed() and see_more_button.is_enabled():
                                    actions = ActionChains(self.driver)
                                    actions.move_to_element(see_more_button).click().perform()
                                    logger.debug("Clicked 'See more description' button to expand job description")
                                    time.sleep(1)  # Wait for expansion animation
                                    break
                        except Exception as button_error:
                            logger.debug(f"Error with selector {selector}: {button_error}")
                            continue
                except Exception as e:
                    logger.debug(f"'See more description' button not found or not clickable: {e}")
                
                # Try multiple selectors for job description to handle different LinkedIn layouts
                description_selectors = [
                    (By.CLASS_NAME, "jobs-description-content__text"),
                    (By.XPATH, "//div[contains(@class, 'jobs-description-content__text')]"),
                    (By.XPATH, "//div[contains(@class, 'jobs-box__html-content')]"),
                    (By.XPATH, "//div[@id='job-details']"),
                    (By.XPATH, "//div[contains(@class, 'jobs-description')]//article")
                ]
                
                description = ""
                for selector_type, selector in description_selectors:
                    try:
                        elements = self.driver.find_elements(selector_type, selector)
                        if elements:
                            for element in elements:
                                if element.is_displayed():
                                    element_text = element.text.strip()
                                    if element_text:
                                        description = element_text
                                        logger.debug(f"Found job description using selector: {selector}")
                                        break
                            if description:
                                break
                    except Exception as desc_error:
                        logger.debug(f"Error with description selector {selector}: {desc_error}")
                        continue
                
                if description:
                    logger.debug("Job description retrieved successfully")
                    return description
                else:
                    # If we still don't have a description, try getting the entire page content as a fallback
                    logger.warning("No job description found with specific selectors, trying to get page content")
                    try:
                        main_content = self.driver.find_element(By.TAG_NAME, "main")
                        description = main_content.text
                        if description:
                            logger.debug("Retrieved job description from main content")
                            return description
                    except Exception as main_error:
                        logger.debug(f"Error getting main content: {main_error}")
                    
                    # If we still don't have a description, refresh the page and try again
                    if attempt < max_attempts:
                        logger.warning(f"No job description found on attempt {attempt}, refreshing page")
                        self.driver.refresh()
                        time.sleep(2)  # Wait for page to reload
                    else:
                        logger.warning("All attempts to get job description failed")
                        utils.capture_screenshot(self.driver, "job_description_all_attempts_failed")
                        return "No job description found after multiple attempts"
            
            except NoSuchElementException as e:
                logger.warning(f"Job description element not found on attempt {attempt}: {e}")
                if attempt < max_attempts:
                    self.driver.refresh()
                    time.sleep(2)
                else:
                    utils.capture_screenshot(self.driver, "job_description_not_found")
                    return "No job description found"
            
            except TimeoutException as te:
                logger.warning(f"Timed out waiting for job description element on attempt {attempt}: {te}")
                if attempt < max_attempts:
                    self.driver.refresh()
                    time.sleep(2)
                else:
                    utils.capture_screenshot(self.driver, "job_description_timeout")
                    return "Job description timed out"
            
            except Exception as e:
                logger.warning(f"Unexpected error in get_job_description on attempt {attempt}: {e}", exc_info=True)
                if attempt < max_attempts:
                    self.driver.refresh()
                    time.sleep(2)
                else:
                    utils.capture_screenshot(self.driver, "job_description_unexpected_error")
                    return "Error getting job description"
        
        # If we've exhausted all attempts and still don't have a description
        logger.error("Failed to retrieve job description after multiple attempts")
        return "Failed to retrieve job description"

    def get_job_salary(self) -> str:
        """
        Retrieves the job salary from the job page.

        Returns:
            str: The job salary text or empty string if not found.
        """
        logger.debug("Getting job salary")
        try:
            salary_element = self.driver.find_element(By.XPATH,"//li[contains(@class, 'job-insight--highlight')]//span[@dir='ltr']")
            salary = salary_element.text.strip()
            if salary:
                logger.debug(f"Job salary retrieved successfully: {salary}")
                return salary
            else:
                logger.warning("Salary element found but text is empty")
                return "Not specified"
        except NoSuchElementException:
            logger.debug("Salary element not found.")
            return ""
        except Exception as e:
            logger.warning(f"Unexpected error in get_job_salary: {e}", exc_info=True)
            return ""

    def get_job_recruiter(self) -> Optional[str]:
        """
        Retrieves the job recruiter information from the job page.
        
        Returns:
            Optional[str]: The recruiter's LinkedIn profile URL or empty string if not found.
        """
        logger.debug("Getting job recruiter information")
        try:
            hiring_team_section = self.wait.until(EC.presence_of_element_located((By.XPATH, '//h2[text()="Meet the hiring team"]')))
            logger.debug("Hiring team section found")

            recruiter_elements = hiring_team_section.find_elements(By.XPATH, './/following::a[contains(@href, "linkedin.com/in/")]')

            if recruiter_elements:
                recruiter_element = recruiter_elements[0]
                recruiter_link = recruiter_element.get_attribute("href")
                logger.debug(f"Job recruiter link retrieved successfully: {recruiter_link}")
                return recruiter_link
            else:
                logger.debug("No recruiter link found in the hiring team section")
                return ""
        except TimeoutException:
            logger.warning("Hiring team section not found within the timeout period")
            return ""
        except Exception as e:
            logger.warning(f"Failed to retrieve recruiter information: {e}", exc_info=True)
            return ""
