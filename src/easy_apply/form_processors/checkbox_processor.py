# src/easy_apply/form_processors/checkbox_processor.py
"""
Module for processing checkbox fields within LinkedIn Easy Apply forms.

Handles finding, evaluating (required, terms, etc.), and interacting with
single or multiple checkboxes within a form section. Includes retry logic
for robustness against dynamic DOM changes.
"""

import time
from typing import List, Optional, TYPE_CHECKING

from loguru import logger
from selenium.common.exceptions import (
    StaleElementReferenceException, TimeoutException,
    ElementNotInteractableException, NoSuchElementException
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC

# Assuming BaseProcessor correctly imports dependencies like WebDriver, LLMProcessor etc.
from .base_processor import BaseProcessor


class CheckboxProcessor(BaseProcessor):
    """
    Processes checkbox elements (`<input type="checkbox">`) within Easy Apply forms.

    Identifies checkboxes, determines if they need to be checked (e.g., required fields,
    agreement checkboxes), and attempts to interact with them using multiple methods
    and retry logic for stability.
    """

    # Keywords indicating a checkbox likely *must* be checked (e.g., agreements)
    REQUIRED_CHECK_KEYWORDS: List[str] = [
        "agree", "terms", "policy", "consent", "accept", "confirm",
        "acknowledge", "authorize", "certify", "understand"
    ]

    def handle(self, element: WebElement, job=None) -> bool:
        """
        Handles checkbox fields found within the provided form section element.

        Args:
            element (WebElement): The WebElement representing the form section
                                  likely containing checkbox(es).
            job (Any): The job object (optional, for interface compatibility).

        Returns:
            bool: True if one or more checkboxes were found and processed
                  (attempted to be checked if necessary), False otherwise.
        """
        logger.debug("CheckboxProcessor: Scanning section for checkboxes...")

        checkbox_inputs: List[WebElement] = []
        processed_any = False

        # --- Find Checkbox Inputs (Multiple Strategies) ---
        strategies = {
            "standard": self.selectors["checkbox"]["standard"],
            "data_test": self.selectors["checkbox"]["data_test"],
            "class_name": f".{self.selectors['checkbox']['class_name']}" # Assuming class is CSS selector here
        }

        for name, selector in strategies.items():
            try:
                locator_type = By.XPATH if selector.startswith(".//") or selector.startswith("/") else By.CSS_SELECTOR
                found_inputs = element.find_elements(locator_type, selector)
                if found_inputs:
                    # Filter only visible inputs
                    checkbox_inputs = [inp for inp in found_inputs if inp.is_displayed()]
                    if checkbox_inputs:
                         logger.debug(f"Found {len(checkbox_inputs)} visible checkbox(es) using strategy '{name}'.")
                         break # Stop searching once checkboxes are found
            except StaleElementReferenceException:
                 logger.warning(f"Stale element reference encountered while searching for checkboxes using strategy '{name}'. Retrying may be needed.")
                 return False # Cannot proceed if container is stale
            except Exception as e:
                 logger.debug(f"Error finding checkboxes using strategy '{name}': {e}", exc_info=False)

        if not checkbox_inputs:
            logger.trace("No visible checkbox inputs found in this section.")
            return False
        # --- End Finding Checkboxes ---


        # --- Process Found Checkboxes ---
        # Usually, checkboxes appear in groups related to one question/statement.
        # Extract the main question/label for context.
        section_question = self.extract_question_text(element) # Get overall section label

        # Determine if the section implies a required choice
        # Use a slightly broader check for required indicators within the section
        is_section_required = False
        try:
            # Check using specific required label class
            if element.find_elements(By.CLASS_NAME, self.selectors["new"]["required_label"]):
                is_section_required = True
            # Check parent elements for required indicators (less reliable)
            # elif element.find_elements(By.XPATH, "./ancestor::*[contains(@class, 'required')]"):
            #     is_section_required = True
            # Check for visual cues like '*' in the label text
            elif "*" in section_question:
                is_section_required = True
        except Exception as e:
            logger.warning(f"Could not determine if checkbox section is required: {e}")

        if is_section_required:
            logger.debug(f"Checkbox section '{section_question}' appears to be required.")


        # Iterate through each checkbox found in the group
        for i, checkbox in enumerate(checkbox_inputs):
            try:
                label_text = self._get_checkbox_label(checkbox, element)
                logger.debug(f"Processing checkbox {i+1}/{len(checkbox_inputs)}: '{label_text}'")

                # Determine if this specific checkbox should be checked
                should_check = False
                if is_section_required:
                    # If section is required, typically check the first non-disabled option,
                    # or specific ones like "Yes" / "Agree" if applicable.
                    # For simplicity here, we check required ones unless they explicitly represent opting out.
                    if "no" not in label_text.lower() and "opt out" not in label_text.lower():
                         should_check = True
                elif any(keyword in label_text.lower() for keyword in self.REQUIRED_CHECK_KEYWORDS):
                    should_check = True # Check if label contains agreement keywords

                # Specific logic: Skip if it's an "opt-out" type checkbox unless required
                is_opt_out = any(term in label_text.lower() for term in ["do not", "opt out", "unsubscribe"])
                if is_opt_out and not is_section_required:
                     should_check = False # Don't check opt-out boxes unless explicitly required

                # Skip disabled checkboxes
                if not checkbox.is_enabled():
                     logger.debug(f"Skipping disabled checkbox: '{label_text}'")
                     continue


                # Perform the check action if needed
                if should_check:
                    logger.info(f"Checkbox '{label_text}' needs to be checked (Required={is_section_required}, Keywords={any(keyword in label_text.lower() for keyword in self.REQUIRED_CHECK_KEYWORDS)}).")
                    if self._process_single_checkbox(element, checkbox, i, label_text):
                        processed_any = True
                    else:
                        logger.warning(f"Failed to process required/agreement checkbox: '{label_text}'. Form submission might fail.")
                        # Optionally raise an error here if checking is critical
                        # raise ElementNotInteractableException(f"Failed to check required checkbox: {label_text}")
                else:
                    logger.debug(f"Skipping optional/non-agreement checkbox: '{label_text}'")
                    processed_any = True # Mark as processed even if skipped

            except StaleElementReferenceException:
                logger.warning(f"Stale element reference for checkbox {i+1}. Skipping.")
                continue # Skip this checkbox
            except Exception as e:
                logger.error(f"Unexpected error processing checkbox {i+1}: {e}", exc_info=True)
                continue # Skip this checkbox on error

        return processed_any


    def _get_checkbox_label(self, checkbox: WebElement, parent_element: WebElement) -> str:
        """Attempts to find the label associated with a specific checkbox input."""
        label_text = "Unknown Checkbox Label"
        try:
            # Strategy 1: Find label using 'for' attribute matching checkbox 'id'
            checkbox_id = checkbox.get_attribute('id')
            if checkbox_id:
                # Search within the parent element for the label
                labels = parent_element.find_elements(By.XPATH, f".//label[@for='{checkbox_id}']")
                if labels and labels[0].text.strip():
                    return labels[0].text.strip()

            # Strategy 2: Find label as sibling or within parent structure
            # Use the more specific relative XPath defined in selectors
            label_elements = checkbox.find_elements(By.XPATH, self.selectors["checkbox"]["label_xpath"])
            if label_elements and label_elements[0].text.strip():
                 return label_elements[0].text.strip()

            # Strategy 3: Fallback - Get text from the immediate parent div/container
            # This is less reliable but can sometimes work
            container = checkbox.find_element(By.XPATH, "./ancestor::div[1]")
            container_text = container.text.strip()
            if container_text:
                 return container_text # Might include more than just the label

        except Exception as e:
            logger.debug(f"Could not reliably determine label for checkbox: {e}")

        return label_text

    def _process_single_checkbox(self, parent_element: WebElement, checkbox: WebElement,
                                index: int, label_text: str) -> bool:
        """
        Processes a single checkbox, attempting to check it if necessary. Includes retry logic.

        Args:
            parent_element (WebElement): The parent container (for re-finding).
            checkbox (WebElement): The checkbox element to process.
            index (int): The index of the checkbox (for re-finding and logging).
            label_text (str): The label text (for logging).

        Returns:
            bool: True if the checkbox was successfully processed (checked or already checked),
                  False if checking failed after retries.
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Re-find element on retries
                if attempt > 0:
                    logger.debug(f"Refreshing checkbox reference (attempt {attempt + 1})")
                    time.sleep(0.5 * attempt) # Small increasing delay
                    # Re-find the checkbox using the original successful strategy (simplified)
                    # This assumes the structure hasn't drastically changed between retries
                    # A more robust way would re-run the finding logic from handle()
                    try:
                         # Simplified re-finding based on index. Assumes order is stable.
                         current_checkboxes = parent_element.find_elements(By.XPATH, self.selectors["checkbox"]["standard"])
                         if index < len(current_checkboxes):
                             checkbox = current_checkboxes[index]
                             logger.debug("Refreshed checkbox element reference.")
                         else:
                             logger.warning("Could not refresh checkbox reference, index out of bounds.")
                             # Try alternative selectors if needed, similar to handle()
                             # ... (add re-finding using other selectors if necessary) ...
                             return False # Cannot retry if element can't be refreshed

                    except Exception as refresh_error:
                        logger.warning(f"Error refreshing checkbox reference: {refresh_error}")
                        continue # Go to next retry attempt

                # Check if already selected
                if checkbox.is_selected():
                    logger.debug(f"Checkbox {index + 1} '{label_text}' is already checked.")
                    return True # Already in desired state

                # Attempt to click (try multiple methods)
                logger.debug(f"Attempting to click checkbox {index + 1} '{label_text}' (attempt {attempt + 1})...")

                # Method 1: Direct click on input
                try:
                    self.wait.until(EC.element_to_be_clickable(checkbox)).click()
                    logger.info(f"Clicked checkbox '{label_text}' (Method: Direct Input Click).")
                    time.sleep(0.2) # Pause for state update
                    if checkbox.is_selected(): return True # Success
                    logger.warning("Direct input click didn't result in selection. Trying JS.")
                except (ElementNotInteractableException, TimeoutException, StaleElementReferenceException):
                    logger.debug("Direct input click failed. Trying JS click.")

                # Method 2: JavaScript click on input
                try:
                    self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true); arguments[0].click();", checkbox)
                    logger.info(f"Clicked checkbox '{label_text}' (Method: JS Input Click).")
                    time.sleep(0.2)
                    if checkbox.is_selected(): return True # Success
                    logger.warning("JS input click didn't result in selection. Trying Label click.")
                except StaleElementReferenceException:
                    raise # Re-raise stale reference to trigger retry
                except Exception as js_err:
                    logger.debug(f"JS input click failed: {js_err}. Trying Label click.")


                # Method 3: Click associated label
                try:
                     label = checkbox.find_element(By.XPATH, self.selectors["checkbox"]["label_xpath"])
                     # Try direct click on label first
                     try:
                          self.wait.until(EC.element_to_be_clickable(label)).click()
                          logger.info(f"Clicked checkbox '{label_text}' (Method: Direct Label Click).")
                          time.sleep(0.2)
                          if checkbox.is_selected(): return True
                          logger.warning("Direct label click failed. Trying JS Label click.")
                     except (ElementNotInteractableException, TimeoutException, StaleElementReferenceException):
                           logger.debug("Direct label click failed. Trying JS Label click.")

                     # Fallback to JS click on label
                     self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true); arguments[0].click();", label)
                     logger.info(f"Clicked checkbox '{label_text}' (Method: JS Label Click).")
                     time.sleep(0.2)
                     if checkbox.is_selected(): return True
                     logger.warning(f"All click methods failed for checkbox '{label_text}' on attempt {attempt + 1}.")

                except NoSuchElementException:
                     logger.warning(f"Could not find label for checkbox '{label_text}' to attempt label click.")
                except StaleElementReferenceException:
                    raise # Re-raise stale reference to trigger retry
                except Exception as label_err:
                    logger.warning(f"Error clicking label for checkbox '{label_text}': {label_err}")


                # If loop continues, click failed on this attempt
                logger.debug(f"Checkbox click attempt {attempt + 1} failed.")


            except StaleElementReferenceException:
                logger.warning(f"Stale element reference encountered for checkbox {index + 1} during attempt {attempt + 1}. Retrying...")
                if attempt == max_retries - 1:
                    logger.error(f"Stale element reference persisted after {max_retries} attempts for checkbox '{label_text}'.")
                    return False # Failed after retries
            except Exception as e:
                logger.warning(f"Unexpected error processing checkbox '{label_text}' on attempt {attempt + 1}: {e}", exc_info=True)
                if attempt == max_retries - 1:
                     logger.error(f"Failed to process checkbox '{label_text}' after {max_retries} attempts due to unexpected errors.")
                     return False # Failed after retries

        # If loop finishes without returning True, checking failed
        logger.error(f"Failed to check checkbox '{label_text}' after {max_retries} attempts.")
        return False