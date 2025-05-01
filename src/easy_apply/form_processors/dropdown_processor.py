# src/easy_apply/form_processors/dropdown_processor.py
"""
Module for processing dropdown (<select>) form fields within LinkedIn Easy Apply forms.

Handles both standard HTML dropdowns and potentially custom implementations found
on the platform. Leverages answer storage and LLM for selecting appropriate options.
"""
from __future__ import annotations 
import time
from typing import List, Optional, Any, TYPE_CHECKING

from loguru import logger
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, StaleElementReferenceException,
    ElementNotInteractableException, UnexpectedTagNameException
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

# Assuming BaseProcessor correctly imports dependencies
from .base_processor import BaseProcessor
# Assuming Job object definition is available
if TYPE_CHECKING:
    from src.job import Job 

else:
    Job: Any = object          



class DropdownProcessor(BaseProcessor):
    """
    Processes dropdown fields (`<select>`) within Easy Apply forms.

    Identifies standard dropdowns, extracts options, determines the best answer
    using cache or LLM, and selects the corresponding option. Includes handling
    for potentially newer/custom dropdown structures if identified.
    """

    # Common placeholder texts to ignore in dropdown options
    PLACEHOLDER_OPTIONS: List[str] = ["select", "choose", "please select", "--"]

    def handle(self, section: WebElement, job: Job) -> bool:
        """
        Finds and handles dropdown fields within the given form section.

        Prioritizes handling known custom structures before falling back to
        standard `<select>` elements.

        Args:
            section (WebElement): The WebElement representing the form section
                                  containing the dropdown.
            job (Job): The job object (used for context if LLM is needed).

        Returns:
            bool: True if a dropdown field was found and successfully handled,
                  False otherwise.
        """
        logger.debug("DropdownProcessor: Scanning section for dropdowns...")

        # --- Strategy 1: Check for specific known custom dropdown containers (e.g., new structure) ---
        # Example using the data-test attribute from selectors (adjust if needed)
        # Note: The original code checked for `select_container` class, adapting to the defined selector.
        new_dropdown_selector = self.selectors["new"]["select_container"]
        try:
            # Assuming selector is CSS attribute selector like '[data-test-...]'
            locator_type = By.CSS_SELECTOR if new_dropdown_selector.startswith('[') else By.XPATH # Basic check
            select_containers = section.find_elements(locator_type, new_dropdown_selector)
            if select_containers:
                logger.debug(f"Found {len(select_containers)} potential 'new structure' dropdown container(s).")
                # Process the first found container
                if self._handle_new_dropdown_structure(section, select_containers[0], job):
                    return True # Successfully handled by new structure logic
                else:
                    logger.warning("Handling via 'new structure' logic failed. Will attempt standard <select> search.")
        except StaleElementReferenceException:
             logger.warning("Stale element reference while searching for new dropdown structure.")
             # Continue to fallback
        except Exception as e:
            logger.debug(f"Error searching for new dropdown structure using '{new_dropdown_selector}': {e}", exc_info=False)
            # Continue to fallback if specific search fails

        # --- Strategy 2: Fallback to standard <select> elements ---
        logger.debug("Searching for standard <select> elements...")
        try:
            dropdowns = section.find_elements(By.TAG_NAME, self.selectors["common"]["select"])
            if not dropdowns:
                logger.trace("No standard <select> element found in this section.")
                return False

            # Process the first visible and enabled dropdown found
            for dropdown in dropdowns:
                if dropdown.is_displayed() and dropdown.is_enabled():
                     logger.debug("Found active standard <select> element.")
                     if self._handle_standard_dropdown(section, dropdown, job):
                         return True # Successfully handled standard dropdown
                     else:
                         logger.warning("Handling standard <select> failed for an active element.")
                         return False # Stop if handling fails for an active element
            logger.debug("No active standard <select> elements found.")
            return False # No active dropdown found

        except StaleElementReferenceException:
             logger.warning("Stale element reference while searching for standard <select> elements.")
             return False
        except Exception as e:
            logger.error(f"Unexpected error searching for standard <select> elements: {e}", exc_info=True)
            return False


    def _handle_standard_dropdown(self, section: WebElement, dropdown: WebElement, job: Job) -> bool:
        """Handles a standard HTML <select> dropdown element."""
        try:
            select = Select(dropdown)
            all_options = [option.text.strip() for option in select.options]
            valid_options = self._filter_valid_options(all_options)

            if not valid_options:
                logger.warning(f"No valid options found in standard dropdown for section: {section.text[:50]}...")
                return False # Cannot proceed without options

            logger.debug(f"Standard dropdown options: {valid_options}")
            question_text = self.extract_question_text(section)

            answer = self._get_answer_for_options(question_text, "dropdown", valid_options, job)
            if not answer:
                 logger.error(f"Could not determine answer for dropdown '{question_text}'.")
                 return False # Cannot proceed without answer

            self._select_dropdown_option(select, answer, valid_options) # Pass Select object
            return True

        except UnexpectedTagNameException:
             logger.error(f"Element passed to Select() was not a <select> tag for section '{section.text[:50]}...'.")
             return False
        except StaleElementReferenceException:
             logger.warning("Stale element reference encountered while handling standard dropdown.")
             return False
        except Exception as e:
            logger.error(f"Error handling standard dropdown: {e}", exc_info=True)
            return False


    def _handle_new_dropdown_structure(self, section: WebElement, select_container: WebElement, job: Job) -> bool:
        """
        Handles dropdown questions potentially using a newer/custom LinkedIn structure.
        (This implementation assumes it still contains a standard <select> tag within the container).
        """
        logger.debug("Attempting to handle dropdown via 'new structure' logic...")
        try:
            # Find the actual <select> element *within* the identified container
            select_element = select_container.find_element(By.TAG_NAME, self.selectors["common"]["select"])
            if not select_element.is_displayed() or not select_element.is_enabled():
                 logger.warning("Found <select> in new container, but it's not active.")
                 return False

            return self._handle_standard_dropdown(section, select_element, job) # Reuse standard logic

        except NoSuchElementException:
            logger.warning("No <select> tag found within the 'new structure' container. Cannot handle as standard dropdown.")
            # Add logic here if the new structure uses divs/spans instead of <select>
            # This would require finding the trigger element, clicking it, waiting for options,
            # finding the options (often <li> or <div>), and clicking the desired one.
            return False # Placeholder: Cannot handle non-standard dropdowns yet
        except StaleElementReferenceException:
            logger.warning("Stale element reference encountered while handling new dropdown structure.")
            return False
        except Exception as e:
            logger.error(f"Error handling new dropdown structure: {e}", exc_info=True)
            return False


    def _filter_valid_options(self, options: List[str]) -> List[str]:
        """Filters out common placeholder options from a list."""
        return [
            opt for opt in options
            if opt and opt.lower() not in self.PLACEHOLDER_OPTIONS and not opt.startswith('--')
        ]


    def _get_answer_for_options(self, question_text: str, question_type: str,
                               options: List[str], job: Job) -> Optional[str]:
        """
        Gets an answer for a question with options (dropdown or radio).

        Checks cache first, then uses LLM, ensuring the answer is valid.

        Args:
            question_text (str): The question text (sanitized).
            question_type (str): 'dropdown' or 'radio'.
            options (List[str]): List of valid, non-placeholder options.
            job (Job): The job object.

        Returns:
            Optional[str]: The best matching answer string from the options list, or None.
        """
        if not options:
             logger.error(f"Cannot get answer for '{question_text}': No valid options provided.")
             return None

        # Check cache
        cached_answer = self.get_existing_answer(question_text, question_type)
        if cached_answer:
            # Verify cached answer is still present in the current options list
            # Use case-insensitive comparison for robustness
            if any(cached_answer.lower() == opt.lower() for opt in options):
                logger.debug(f"Using valid cached answer for '{question_text}': '{cached_answer}'")
                # Return the exact matching option from the current list to preserve casing
                return next((opt for opt in options if cached_answer.lower() == opt.lower()), cached_answer)
            else:
                logger.warning(f"Cached answer '{cached_answer}' for '{question_text}' is not in current valid options: {options}. Regenerating.")

        # Generate new answer using LLM
        logger.debug(f"Querying LLM for best option for '{question_text}' from {options}...")
        try:
             # Ensure LLM processor is available
             if not hasattr(self.llm_processor, 'answer_question_from_options'):
                 logger.error("LLMProcessor does not have 'answer_question_from_options' method.")
                 return None # Cannot generate

             llm_selected_option = self.llm_processor.answer_question_from_options(question_text, options)

             if llm_selected_option and isinstance(llm_selected_option, str):
                 # Verify LLM answer is one of the provided options (case-insensitive check)
                 match = next((opt for opt in options if llm_selected_option.lower() == opt.lower()), None)
                 if match:
                     logger.info(f"LLM selected option for '{question_text}': '{match}'")
                     self.save_answer(question_text, question_type, match) # Save the matched option
                     return match
                 else:
                      logger.warning(f"LLM suggestion '{llm_selected_option}' is not exactly in valid options {options}. Trying partial match or fallback.")
                      # Optional: Implement fuzzy matching here if needed (e.g., using Levenshtein distance)
                      # Fallback: Select first option? Or None? Selecting first is safer for required fields.
                      fallback_answer = options[0]
                      logger.warning(f"Falling back to first option: '{fallback_answer}'")
                      self.save_answer(question_text, question_type, fallback_answer) # Save fallback
                      return fallback_answer

             else:
                  logger.error(f"LLM did not return a valid string answer for '{question_text}'.")
                  # Fallback to first option if LLM fails
                  fallback_answer = options[0]
                  logger.warning(f"Falling back to first option due to LLM failure: '{fallback_answer}'")
                  self.save_answer(question_text, question_type, fallback_answer) # Save fallback
                  return fallback_answer

        except Exception as e:
             logger.error(f"Error getting answer via LLM for '{question_text}': {e}", exc_info=True)
             # Fallback to first option on error
             fallback_answer = options[0]
             logger.warning(f"Falling back to first option due to LLM error: '{fallback_answer}'")
             self.save_answer(question_text, question_type, fallback_answer) # Save fallback
             return fallback_answer


    def _select_dropdown_option(self, select_obj: Select, text_to_select: str, available_options: List[str]) -> None:
        """
        Selects a specific option from a dropdown using the Select object.

        Args:
            select_obj (Select): The initialized Selenium Select object.
            text_to_select (str): The visible text of the option to select.
            available_options (List[str]): The list of valid option texts (for error msg).

        Raises:
            ValueError: If the specified text cannot be found or selected.
            StaleElementReferenceException: If the dropdown becomes stale.
            Exception: For other Selenium errors during selection.
        """
        logger.debug(f"Attempting to select dropdown option by visible text: '{text_to_select}'")

        try:
            select_obj.select_by_visible_text(text_to_select)
            # Verification step
            time.sleep(0.3) # Short pause for selection to register visually/in DOM
            selected_option_text = select_obj.first_selected_option.text.strip()

            if selected_option_text.lower() == text_to_select.lower():
                logger.info(f"Successfully selected dropdown option: '{text_to_select}'")
            else:
                # This case should ideally not happen if select_by_visible_text succeeded without error,
                # but verification adds robustness.
                logger.error(f"Selection verification failed! Expected '{text_to_select}', but found '{selected_option_text}'.")
                raise ValueError(f"Failed to verify selection of '{text_to_select}'")

        except NoSuchElementException:
            logger.error(f"Option '{text_to_select}' not found by visible text in dropdown. Available: {available_options}")
            # Optional: Try partial match or selection by value/index as fallback?
            raise ValueError(f"Option '{text_to_select}' not found in dropdown.") from None
        except StaleElementReferenceException:
             logger.error("Dropdown element became stale during selection.")
             raise # Re-raise stale exception
        except Exception as e:
            logger.error(f"Failed to select dropdown option '{text_to_select}': {e}", exc_info=True)
            raise # Re-raise other exceptions