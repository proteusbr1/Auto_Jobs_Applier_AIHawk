# src/easy_apply/form_processors/radio_processor.py
"""
Module for processing radio button form fields within LinkedIn Easy Apply forms.

Handles identifying radio button groups, extracting options, determining the
appropriate selection using cache or LLM, and interacting with the elements.
"""
from __future__ import annotations 
import time
from typing import List, Optional, Tuple, Any, TYPE_CHECKING

from loguru import logger
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, StaleElementReferenceException,
    ElementNotInteractableException
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains


# Assuming BaseProcessor correctly imports dependencies
from .base_processor import BaseProcessor
# Assuming Job object definition is available
if TYPE_CHECKING:
    from src.job import Job 
else:
    Job: Any = object          


if TYPE_CHECKING:
    from src.job import Job 
else:
    Job: Any = object          


# Assuming DropdownProcessor has the shared answer logic
try:
    from .dropdown_processor import DropdownProcessor
except ImportError:
     logger.error("Failed relative import of DropdownProcessor. Replicating answer logic.")
     # Replicate the necessary method if import fails
     class DropdownProcessor(BaseProcessor): # type: ignore
         def _get_answer_for_options(self, question_text: str, question_type: str,
                               options: List[str], job: Job) -> Optional[str]:
                # Placeholder implementation - real one needed if import fails
                logger.warning("Using placeholder _get_answer_for_options.")
                if options: return options[0]
                return None


class RadioProcessor(BaseProcessor):
    """
    Processes radio button groups within Easy Apply forms.

    Handles both older and potentially newer structures for radio buttons,
    selects the appropriate option based on stored answers or LLM generation.
    """

    def handle(self, section: WebElement, job: Job) -> bool:
        """
        Finds and handles radio button groups within the given form section.

        Tries to identify radio buttons using selectors for different potential
        LinkedIn UI structures.

        Args:
            section (WebElement): The WebElement representing the form section
                                  containing the radio buttons.
            job (Job): The job object (used for context if LLM is needed).

        Returns:
            bool: True if a radio button group was found and successfully handled,
                  False otherwise.
        """
        logger.debug("RadioProcessor: Scanning section for radio button groups...")

        handled = False
        # --- Strategy 1: Try New Structure (using data-test attributes / fieldset) ---
        try:
            # Check if section contains the specific fieldset for new radio groups
            fieldset_selector = self.selectors["new"]["radio_fieldset"]
            # Assuming selector is CSS attribute selector like '[data-test-...="true"]'
            locator_type = By.CSS_SELECTOR if fieldset_selector.startswith('[') else By.XPATH
            fieldsets = section.find_elements(locator_type, fieldset_selector)

            if fieldsets:
                logger.debug(f"Found {len(fieldsets)} potential 'new structure' radio fieldset(s).")
                # Process the first found fieldset
                if self._handle_new_radio_structure(fieldsets[0], job):
                    handled = True
                else:
                     logger.warning("Handling via 'new structure' radio logic failed.")
                     # Potentially fallback? Or assume only one structure exists per section?
                     # For now, return False if new structure handling fails.
                     return False
        except StaleElementReferenceException:
             logger.warning("Stale element reference while searching for new radio structure.")
             return False # Cannot proceed if container is stale
        except Exception as e:
            logger.debug(f"Did not find or failed processing 'new structure' radio fieldset: {e}", exc_info=False)
            # Continue to try old structure

        if handled:
            return True

        # --- Strategy 2: Try Old Structure (using specific class names) ---
        if not handled:
            logger.debug("Searching for 'old structure' radio buttons...")
            try:
                 # Old structure often had options directly within a form element container
                 option_selector = f".{self.selectors['old']['radio_option']}" # Assuming class name
                 radio_options = section.find_elements(By.CSS_SELECTOR, option_selector)

                 if radio_options and len(radio_options) > 1: # Need at least 2 options for radios
                     logger.debug(f"Found {len(radio_options)} potential 'old structure' radio options.")
                     if self._handle_old_radio_structure(section, radio_options, job):
                         handled = True
                     else:
                          logger.warning("Handling via 'old structure' radio logic failed.")
                          return False # Stop if handling fails
                 else:
                     logger.trace("No 'old structure' radio options found.")

            except StaleElementReferenceException:
                 logger.warning("Stale element reference while searching for old radio structure.")
                 return False
            except Exception as e:
                logger.error(f"Error searching/handling 'old structure' radio buttons: {e}", exc_info=True)
                return False # Stop if unexpected error occurs

        # Return final status
        if not handled:
            logger.trace("No radio button groups handled in this section.")
        return handled


    def _handle_new_radio_structure(self, fieldset: WebElement, job: Job) -> bool:
        """Handles radio buttons found within the newer fieldset structure."""
        logger.debug("Processing 'new structure' radio group...")
        try:
            # Extract question text from the legend within the fieldset
            legend = fieldset.find_element(By.TAG_NAME, "legend")
            # Get text content robustly, handling potential nested spans/elements
            question_text = self.driver.execute_script("return arguments[0].textContent;", legend).strip()
            # Fallback if JS fails
            if not question_text: question_text = legend.text.strip()

            question_text_sanitized = self.answer_storage.sanitize_text(question_text)
            logger.debug(f"Question text (New Radio): '{question_text_sanitized}'")

            # Find all radio option containers within the fieldset
            option_container_selector = self.selectors["new"]["radio_option_container"]
            # Assuming selector might be CSS or XPath based on definition
            locator_type = By.CSS_SELECTOR if not option_container_selector.startswith(('/', '.')) else By.XPATH
            option_containers = fieldset.find_elements(locator_type, option_container_selector)

            if not option_containers or len(option_containers) < 2:
                 logger.warning("Found new radio fieldset but < 2 option containers inside.")
                 return False

            options_data: List[Tuple[str, WebElement, WebElement]] = [] # (label_text, input_element, label_element)
            for container in option_containers:
                try:
                    # Extract label and input using specific data-test attributes (more stable)
                    # Assuming XPath attributes like @data-test-...
                    input_attr = self.selectors['new']['radio_input']
                    label_attr = self.selectors['new']['radio_label']
                    radio_input = container.find_element(By.XPATH, f".//input[{input_attr}]")
                    radio_label_element = container.find_element(By.XPATH, f".//label[{label_attr}]")
                    # Get label text robustly
                    label_text = self.driver.execute_script("return arguments[0].textContent;", radio_label_element).strip()
                    if not label_text: label_text = radio_label_element.text.strip()

                    if label_text: # Only add if label is found
                        options_data.append((label_text, radio_input, radio_label_element))
                    else:
                         logger.warning("Found radio option container but could not extract label text.")
                except NoSuchElementException:
                    logger.warning("Could not find input or label element within a radio option container using data-test attributes.")
                    continue # Skip this malformed option
                except Exception as extract_err:
                    logger.warning(f"Error extracting data from radio option container: {extract_err}")
                    continue # Skip this option

            if not options_data:
                logger.error("Failed to extract any valid options from the new radio structure fieldset.")
                return False

            option_labels = [opt[0] for opt in options_data]
            logger.debug(f"Available options (New Radio): {option_labels}")

            # Get the answer using shared logic (treat like dropdown options)
            # Reuse the logic from DropdownProcessor by creating an instance or importing it
            dp = DropdownProcessor(self.driver, self.llm_processor, self.answer_storage, self.wait_time)
            answer = dp._get_answer_for_options(question_text_sanitized, "radio", option_labels, job) # type: ignore

            if not answer:
                logger.error(f"Could not determine answer for radio question '{question_text_sanitized}'.")
                return False # Cannot proceed

            # Select the radio button corresponding to the answer
            selected = False
            for i, (label, radio_input, radio_label) in enumerate(options_data):
                 # Use case-insensitive comparison
                 if answer.lower() == label.lower():
                     if self._select_radio_option(radio_input, radio_label, label):
                         selected = True
                         break # Stop after selecting the correct option

            if not selected:
                 logger.error(f"Failed to select the desired radio option '{answer}' for question '{question_text_sanitized}'.")
                 # Optionally, try selecting the first option as a fallback if selection is critical
                 # logger.warning("Attempting to select first option as fallback...")
                 # if self._select_radio_option(options_data[0][1], options_data[0][2], options_data[0][0]):
                 #     logger.info("Selected first radio option as fallback.")
                 #     return True # Mark as handled if fallback worked
                 return False # Failed to select desired or fallback

            return True # Successfully selected the option

        except NoSuchElementException:
            logger.debug("Required elements (legend, options) not found within new radio fieldset.")
            return False
        except StaleElementReferenceException:
             logger.warning("Stale element reference encountered while handling new radio structure.")
             return False
        except Exception as e:
            logger.error(f"Error processing 'new structure' radio group: {e}", exc_info=True)
            return False


    def _handle_old_radio_structure(self, section: WebElement, radio_options: List[WebElement], job: Job) -> bool:
        """Handles radio buttons found using the older class name structure."""
        logger.debug("Processing 'old structure' radio group...")
        try:
            question_text_sanitized = self.extract_question_text(section) # Reuse base extraction
            logger.debug(f"Question text (Old Radio): '{question_text_sanitized}'")

            option_labels = []
            option_elements_map = {} # Map label text back to element for clicking
            for option_element in radio_options:
                try:
                     # Old structure often had label directly inside the option container
                     label_element = option_element.find_element(By.TAG_NAME, self.selectors["common"]["label"])
                     label_text = label_element.text.strip()
                     if label_text:
                         option_labels.append(label_text)
                         option_elements_map[label_text.lower()] = label_element # Store label element for click
                     else:
                         logger.warning("Found old radio option element but label text is empty.")
                except NoSuchElementException:
                     logger.warning("Could not find label within old radio option element.")
                     # Fallback: use option element's text if label not found?
                     container_text = option_element.text.strip()
                     if container_text:
                          option_labels.append(container_text)
                          option_elements_map[container_text.lower()] = option_element # Use container for click
                except Exception as extract_err:
                     logger.warning(f"Error extracting text/label from old radio option: {extract_err}")

            if not option_labels:
                 logger.error("Failed to extract any valid options from the old radio structure elements.")
                 return False

            logger.debug(f"Available options (Old Radio): {option_labels}")

            # Get answer using shared logic
            dp = DropdownProcessor(self.driver, self.llm_processor, self.answer_storage, self.wait_time)
            answer = dp._get_answer_for_options(question_text_sanitized, "radio", option_labels, job) # type: ignore

            if not answer:
                 logger.error(f"Could not determine answer for radio question '{question_text_sanitized}'.")
                 return False

            # Select the radio button by clicking its associated label/container element
            click_element = option_elements_map.get(answer.lower())
            if click_element:
                try:
                    # Use robust click (JS often needed for labels covering inputs)
                    self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true); arguments[0].click();", click_element)
                    logger.info(f"Selected radio option '{answer}' for '{question_text_sanitized}' (Old Structure).")
                    return True
                except Exception as click_err:
                    logger.error(f"Failed to click selected radio option element (Old Structure): {click_err}", exc_info=True)
                    return False
            else:
                 logger.error(f"Could not find element to click for selected answer '{answer}' (Old Structure). This should not happen.")
                 return False # Mapping failed

        except StaleElementReferenceException:
            logger.warning("Stale element reference encountered while handling old radio structure.")
            return False
        except Exception as e:
            logger.error(f"Error processing 'old structure' radio group: {e}", exc_info=True)
            return False


    def _select_radio_option(self, radio_input: WebElement, radio_label: WebElement, label_text: str) -> bool:
        """Attempts to select a radio button using multiple click methods."""
        max_retries = 2 # Slightly fewer retries for clicks within handler
        for attempt in range(max_retries):
            logger.debug(f"Attempting to select radio '{label_text}' (Attempt {attempt + 1})")
            try:
                # Ensure element is in view
                self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", radio_input)
                time.sleep(0.1)

                # Check if already selected (using JS for reliability)
                if self.driver.execute_script("return arguments[0].checked;", radio_input):
                    logger.debug(f"Radio button '{label_text}' is already selected.")
                    return True

                # --- Click Attempts ---
                # 1. JS Click on Input (often most reliable for radios hidden by labels)
                try:
                     self.driver.execute_script("arguments[0].click();", radio_input)
                     time.sleep(0.2)
                     if self.driver.execute_script("return arguments[0].checked;", radio_input):
                         logger.info(f"Selected radio '{label_text}' via JS Input Click.")
                         return True
                     logger.debug("JS Input click didn't select. Trying Label click.")
                except StaleElementReferenceException: raise # Propagate stale exception for retry
                except Exception: logger.debug("JS Input click failed.")

                # 2. JS Click on Label
                try:
                     self.driver.execute_script("arguments[0].click();", radio_label)
                     time.sleep(0.2)
                     if self.driver.execute_script("return arguments[0].checked;", radio_input):
                         logger.info(f"Selected radio '{label_text}' via JS Label Click.")
                         return True
                     logger.debug("JS Label click didn't select. Trying standard click.")
                except StaleElementReferenceException: raise
                except Exception: logger.debug("JS Label click failed.")


                # 3. Standard Click on Label (might be intercepted)
                try:
                     self.wait.until(EC.element_to_be_clickable(radio_label)).click()
                     time.sleep(0.2)
                     if self.driver.execute_script("return arguments[0].checked;", radio_input):
                         logger.info(f"Selected radio '{label_text}' via Standard Label Click.")
                         return True
                     logger.debug("Standard Label click didn't select. Trying ActionChains.")
                except (ElementNotInteractableException, TimeoutException): logger.debug("Standard Label click failed.")
                except StaleElementReferenceException: raise


                 # 4. Action Chains Click on Input (last resort)
                try:
                     actions = ActionChains(self.driver)
                     actions.move_to_element(radio_input).click().perform()
                     time.sleep(0.2)
                     if self.driver.execute_script("return arguments[0].checked;", radio_input):
                         logger.info(f"Selected radio '{label_text}' via ActionChains Click.")
                         return True
                     logger.warning(f"ActionChains click failed to select radio '{label_text}'.")
                except StaleElementReferenceException: raise
                except Exception as action_err: logger.debug(f"ActionChains click failed: {action_err}")

                # If we reach here, all methods failed for this attempt
                logger.warning(f"All click methods failed for radio '{label_text}' on attempt {attempt + 1}.")
                if attempt < max_retries - 1:
                     time.sleep(0.5) # Wait before retrying

            except StaleElementReferenceException:
                 logger.warning(f"Stale element reference on attempt {attempt + 1} for radio '{label_text}'. Retrying...")
                 if attempt == max_retries - 1:
                      logger.error(f"Stale element reference persisted after {max_retries} attempts for radio '{label_text}'.")
                      return False
                 time.sleep(0.5 * (attempt + 1)) # Increasing wait
            except Exception as e:
                 logger.error(f"Unexpected error during radio select attempt {attempt + 1} for '{label_text}': {e}", exc_info=True)
                 return False # Stop trying on unexpected errors

        logger.error(f"Failed to select radio button '{label_text}' after {max_retries} attempts.")
        return False