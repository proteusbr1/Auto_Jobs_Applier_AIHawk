"""
Module for handling form navigation and interaction in LinkedIn Easy Apply forms.
"""
import time
from typing import List, Optional
from loguru import logger
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementNotInteractableException,
)
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import src.utils as utils
from src.job import Job

class FormHandler:
    """
    Handles form navigation and interaction in LinkedIn Easy Apply forms.
    """
    
    def __init__(self, driver: WebDriver, wait_time: int = 10):
        """
        Initialize the FormHandler with a WebDriver instance.
        
        Args:
            driver (WebDriver): The Selenium WebDriver instance.
            wait_time (int): The maximum time to wait for elements to appear.
        """
        self.driver = driver
        self.wait = WebDriverWait(self.driver, wait_time)
    
    def handle_job_search_safety_reminder(self) -> None:
        """
        Handles the 'Job search safety reminder' modal if it appears.
        """
        try:
            modal = self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "artdeco-modal")))
            logger.debug("Job search safety reminder modal detected.")
            continue_button = modal.find_element(By.XPATH, '//button[contains(., "Continue applying")]')
            if continue_button:
                continue_button.click()
                logger.debug("Clicked 'Continue applying' button in modal.")
        except NoSuchElementException:
            logger.debug("Job search safety reminder elements not found.")
        except TimeoutException:
            logger.debug("No 'Job search safety reminder' modal detected.")
        except Exception as e:
            logger.warning(f"Unexpected error while handling safety reminder modal: {e}", exc_info=True)
    
    def scroll_page(self) -> None:
        """
        Scrolls the page up and down to ensure all elements are loaded.
        """
        logger.debug("Scrolling the page")
        try:
            scrollable_element = self.driver.find_element(By.TAG_NAME, "html")
            utils.scroll_slow(self.driver, scrollable_element, step=300, reverse=False)
            utils.scroll_slow(self.driver, scrollable_element, step=300, reverse=True)
            logger.debug("Page scrolled successfully")
        except Exception as e:
            logger.warning(f"Failed to scroll the page: {e}", exc_info=True)
    
    def click_easy_apply_buttons_sequentially(self, job: Job) -> bool:
        """
        Attempts to click each 'Easy Apply' button found sequentially.
        
        Args:
            job (Job): The job object containing job details.
            
        Returns:
            bool: True if the application is successful, False otherwise.
        """
        buttons = self._find_easy_apply_buttons(job)
        
        if not buttons:
            logger.error("No 'Easy Apply' button found.")
            return False
        
        for index, button in enumerate(buttons, start=1):
            try:
                logger.debug(f"Trying to click 'Easy Apply' button number {index}.")

                if not self._is_element_clickable(button):
                    logger.debug(f"'Easy Apply' button number {index} is not clickable.")
                    continue

                ActionChains(self.driver).move_to_element(button).click().perform()
                logger.debug(f"Successfully clicked 'Easy Apply' button number {index}.")
                
                # Check if the modal opened correctly
                if self._is_modal_displayed():
                    logger.debug("The 'Easy Apply' modal displayed successfully.")
                    return True
                else:
                    logger.debug("The 'Easy Apply' modal did not display after clicking.")
                    self.driver.refresh()
                    continue  # Try the next button
                    
            except (NoSuchElementException, ElementNotInteractableException, TimeoutException) as e:
                self.driver.refresh()
                continue  # Try the next button
        
        logger.error("All 'Easy Apply' buttons clicked failed.")
        return False
    
    def _find_easy_apply_buttons(self, job: Job) -> List[WebElement]:
        """
        Finds all 'Easy Apply' buttons corresponding to the specific job.
        
        Args:
            job (Job): The job object containing job details.
            
        Returns:
            List[WebElement]: List of WebElements of the found 'Easy Apply' buttons.
        """
        logger.debug(f"Searching for 'Easy Apply' buttons for job ID: {job.link}")
        
        # More specific XPath using data-job-id
        # xpath = f'//button[@data-job-id="{job.link}" and contains(@aria-label, "Easy Apply")]'
        xpath = '//button[contains(@aria-label, "Easy Apply") and contains(@class, "jobs-apply-button")]'
        
        try:
            buttons = self.wait.until(lambda d: d.find_elements(By.XPATH, xpath))
            logger.debug(f"Number of 'Easy Apply' buttons found: {len(buttons)}")
            return buttons
        except TimeoutException:
            logger.warning(f"No 'Easy Apply' button found for job ID: {job.link}")
            return []
    
    def _is_element_clickable(self, element: WebElement) -> bool:
        """
        Checks if a given WebElement is clickable.

        Args:
            element (WebElement): The WebElement to check.
            
        Returns:
            bool: True if the element is clickable, False otherwise.
        """
        try:
            self.wait.until(EC.visibility_of(element))
            self.wait.until(EC.element_to_be_clickable(element))
            logger.debug("Element is visible and clickable.")
            return True
        except Exception as e:
            logger.debug(f"Element is not clickable: {e}")
            return False
    
    def _is_modal_displayed(self) -> bool:
        """
        Checks if the '.artdeco-modal' is displayed.
        
        Returns:
            bool: True if the modal is visible, False otherwise.
        """
        try:
            modal = self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".artdeco-modal")))
            logger.debug("Modal found and visible.")
            return modal.is_displayed()
        except TimeoutException:
            logger.debug("The '.artdeco-modal' not found or is not visible.")
            return False
        except Exception as e:
            logger.error(f"Error checking the modal: {e}", exc_info=True)
            return False
    
    def next_or_submit(self) -> bool:
        """
        Clicks on 'Next', 'Review', or 'Submit' button in the application form.

        Returns:
            bool: True if application is submitted, False otherwise.
        """
        logger.debug("Starting attempt to click on 'Next', 'Review', or 'Submit'")
        try:
            buttons = self.driver.find_elements(By.CLASS_NAME, "artdeco-button--primary")
            logger.debug(f"Found {len(buttons)} primary buttons.")
            
            if not buttons:
                logger.error("No primary button found on the page.")
                utils.capture_screenshot(self.driver, "no_primary_buttons_found")
                return False

            # Prioritize 'Submit application'
            for button in buttons:
                button_text = button.text.strip().lower()
                if "submit application" in button_text:
                    logger.debug("Found 'Submit application' button.")
                    self._unfollow_company()
                    logger.debug("Clicking on the 'Submit application' button.")
                    button.click()
                    logger.debug("Clicked 'Submit application' button. Waiting for page update.")
                    self.wait.until(EC.staleness_of(button))
                    logger.debug("Application submitted successfully.")
                    return True

            # If 'Submit application' is not found, try 'Next' or 'Review'
            for button in buttons:
                button_text = button.text.strip().lower()
                if "next" in button_text or "review" in button_text:
                    logger.debug(f"Found '{button_text}' button.")
                    logger.debug(f"Clicking on the '{button.text.strip()}' button.")
                    button.click()
                    logger.debug(f"Clicked '{button_text}' button. Waiting for next section.")
                    time.sleep(1)
                    self._check_for_errors()
                    return False

            # No expected button found
            logger.error("No 'Submit application', 'Next', or 'Review' button was found.")
            # Print all buttons
            for button in buttons:
                button_text = button.text.strip().lower()
                logger.error(f"Button text: {button_text}")
            
            utils.capture_screenshot(self.driver, "no_submit_next_or_review_button_found")
            return False

        except Exception as e:
            logger.error(f"Error in the next_or_submit function: {e}", exc_info=True)
            utils.capture_screenshot(self.driver, "error_in_next_or_submit")
            # Log the current URL for debugging
            current_url = self.driver.current_url
            logger.error(f"Current job URL when error occurred: {current_url}")
            return False
    
    def _unfollow_company(self) -> None:
        """
        Unfollows the company to avoid staying updated with their page.
        """
        try:
            logger.debug("Unfollowing company to avoid staying updated with their page")
            follow_checkbox = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(.,'to stay up to date with their page.')]")))
            follow_checkbox.click()
            logger.debug("Unfollowed company successfully")
        except TimeoutException:
            logger.warning("Unfollow checkbox not found within the timeout period, possibly already unfollowed")
            utils.capture_screenshot(self.driver, "unfollow_checkbox_timeout")
        except Exception as e:
            logger.warning(f"Failed to unfollow company: {e}", exc_info=True)
    
    def _check_for_errors(self) -> None:
        """
        Checks for form errors after clicking 'Next' or 'Review'.
        """
        logger.debug("Checking for form errors")
        try:
            # Check for errors in the old HTML structure
            error_elements = self.driver.find_elements(By.CLASS_NAME, "artdeco-inline-feedback--error")
            
            # Check for errors in the new HTML structure
            if not error_elements:
                # Look for any elements with error messages
                error_elements = self.driver.find_elements(By.XPATH, "//*[contains(@id, '-error')]")
                
                # Filter out empty error elements
                error_elements = [e for e in error_elements if e.text.strip()]
            
            if error_elements:
                error_texts = []
                field_errors = {}
                
                # Collect error messages with their associated field labels
                for error_element in error_elements:
                    error_text = error_element.text.strip()
                    if not error_text:
                        continue
                        
                    error_texts.append(error_text)
                    
                    # Try to find the associated field label
                    try:
                        # Get the error element ID to find the related field
                        error_id = error_element.get_attribute("id")
                        if error_id:
                            # Extract the field ID from the error ID
                            field_id = error_id.replace("-error", "")
                            
                            # Try to find the field element
                            field_element = self.driver.find_element(By.ID, field_id)
                            
                            # Find the closest label
                            label_element = None
                            
                            # Try to find label by looking at parent elements
                            parent = field_element.find_element(By.XPATH, "./..")
                            label_elements = parent.find_elements(By.TAG_NAME, "label")
                            
                            if not label_elements:
                                # Try to find label by looking at grandparent elements
                                parent = parent.find_element(By.XPATH, "./..")
                                label_elements = parent.find_elements(By.TAG_NAME, "label")
                            
                            if label_elements:
                                label_element = label_elements[0]
                                label_text = label_element.text.strip()
                                field_errors[label_text] = error_text
                    except Exception as label_error:
                        logger.debug(f"Could not find label for error: {error_text}. Error: {label_error}")
                
                # Log detailed error information
                if field_errors:
                    logger.error(f"Form submission failed with specific field errors:")
                    for field, error in field_errors.items():
                        logger.error(f"  - Field '{field}': {error}")
                
                logger.error(f"Form submission failed with errors: {error_texts}")
                
                # Log the current URL for debugging
                current_url = self.driver.current_url
                logger.error(f"Current job URL when error occurred: {current_url}")
                
                # Create a more detailed error message
                if field_errors:
                    detailed_errors = [f"Field '{field}': {error}" for field, error in field_errors.items()]
                    raise Exception(f"Failed answering or file upload. Specific errors: {detailed_errors}")
                else:
                    raise Exception(f"Failed answering or file upload. {error_texts}")
            else:
                logger.debug("No form errors detected")
        except Exception as e:
            logger.error(f"Error while checking for form errors: {e}", exc_info=True)
            raise
    
    def discard_application(self) -> None:
        """
        Discards the current application process.
        """
        logger.debug("Discarding application")
        try:
            dismiss_button = self.wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "artdeco-modal__dismiss")))
            dismiss_button.click()
            logger.debug("Clicked dismiss button on application modal")
            self.wait.until(EC.staleness_of(dismiss_button))

            confirm_buttons = self.driver.find_elements(By.CLASS_NAME, "artdeco-modal__confirm-dialog-btn")
            if confirm_buttons:
                self.wait.until(EC.element_to_be_clickable(confirm_buttons[0]))
                confirm_buttons[0].click()
                logger.debug("Confirmed discarding application")
                self.wait.until(EC.staleness_of(confirm_buttons[0]))
            else:
                logger.warning("Confirm discard button not found")
        except TimeoutException:
            logger.warning("Discard modal elements not found within the timeout period")
        except Exception as e:
            logger.warning(f"Failed to discard application: {e}", exc_info=True)
