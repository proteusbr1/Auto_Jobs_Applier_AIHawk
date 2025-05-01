# src/easy_apply/form_processors/typeahead_processor.py
"""
Processor for handling typeahead (autocomplete) input fields commonly found
in LinkedIn Easy Apply forms (e.g., for location, skills, school names).
"""
from __future__ import annotations 
import time
from typing import Optional, Any, TYPE_CHECKING

from loguru import logger
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, StaleElementReferenceException,
    ElementNotInteractableException, WebDriverException
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait # Import specifically

# Assuming BaseProcessor correctly imports dependencies
from .base_processor import BaseProcessor
# Assuming Job object definition is available
if TYPE_CHECKING:
    from src.job import Job 
else:
    Job: Any = object          
# Assuming LLMError is defined
try:
    from src.llm import LLMError
except ImportError:
     logger.warning("LLMError not found, using base Exception for LLM issues.")
     LLMError = Exception # type: ignore

# Import utils for screenshot capability
try:
    import src.utils as utils
except ImportError:
    logger.warning("src.utils not found, screenshot capability on error disabled in TypeaheadProcessor.")
    utils = None # type: ignore


class TypeaheadProcessor(BaseProcessor):
    """
    Handles typeahead/autocomplete input fields where users type and select
    from a dynamically appearing list of suggestions.
    """

    # XPaths for suggestion container and individual options (adjust if UI changes)
    SUGGESTION_CONTAINER_XPATH: str = ".//div[contains(@class,'basic-typeahead__triggered-content') or contains(@class,'typeahead-suggestions') or contains(@class,'pac-container') or contains(@class, 'artdeco-typeahead__results-list')]" # Added artdeco class
    SUGGESTION_OPTION_XPATH: str = ".//li[contains(@class,'basic-typeahead__selectable') or contains(@class,'typeahead-suggestion') or contains(@class,'pac-item') or contains(@class, 'artdeco-typeahead__result')]" # Added artdeco class
    SUGGESTION_OPTION_ACTIVE_XPATH: str = ".//li[contains(@class, 'active') or contains(@class,'selected') or contains(@class,'--active') or contains(@class, 'artdeco-typeahead__result--selected')]" # Added artdeco class

    # Fallback answer if LLM fails
    FALLBACK_TYPEAHEAD_ANSWER: str = "" # Often better to leave blank than guess wrong

    def handle(self, section: WebElement, job: Job) -> bool:
        """
        Finds and handles a typeahead input field within the given section.

        Args:
            section (WebElement): The WebElement representing the form section.
            job (Job): The job object for context.

        Returns:
            bool: True if a typeahead field was found and handled, False otherwise.
        """
        logger.debug("TypeaheadProcessor: Scanning section for typeahead field.")

        try:
            xpath = self.selectors["common"]["typeahead"]
            # Find potential fields, prioritize visible/enabled ones
            potential_fields = section.find_elements(By.XPATH, xpath)
            field: Optional[WebElement] = None
            for pf in potential_fields:
                 if pf.is_displayed() and pf.is_enabled():
                     field = pf
                     break # Use the first active one

            if not field:
                logger.trace("No active typeahead field found in this section.")
                return False

            logger.debug("Found active typeahead field.")
            # Wait briefly for field to be fully ready
            self.wait.until(EC.visibility_of(field))
            self.wait.until(EC.element_to_be_clickable(field))

            question = self.extract_question_text(section)
            logger.debug(f"Typeahead question identified: '{question}'")

            answer = self._get_typeahead_answer(question, job)
            if answer is None: # Handle LLM failure
                 logger.error(f"Could not determine answer for typeahead '{question}'. Skipping.")
                 return False

            # Special case: If answer is empty/fallback, don't attempt to fill, might cause errors.
            if not answer or answer == self.FALLBACK_TYPEAHEAD_ANSWER:
                 logger.warning(f"Answer for typeahead '{question}' is empty or fallback. Skipping fill attempt.")
                 # Return True because we identified it, but didn't fill. Or False? Depends on requirement.
                 # Returning False as no action was taken.
                 return False

            # Proceed to fill and select
            self._fill_and_select(field, answer, question)
            # Note: _fill_and_select raises errors on failure, so reaching here implies success.
            logger.info(f"Filled typeahead '{question}' successfully.")
            return True

        except StaleElementReferenceException:
             logger.warning("Stale element reference encountered while handling typeahead.")
             return False
        except (TimeoutException, ElementNotInteractableException) as e:
             logger.error(f"Typeahead field not ready for interaction: {e.__class__.__name__}")
             return False
        except RuntimeError as e: # Catch specific error raised by _fill_and_select
             logger.error(f"Typeahead fill/select process failed for '{question}': {e}")
             return False
        except Exception as e:
            logger.error(f"Unexpected error handling typeahead field: {e}", exc_info=True)
            return False


    def _get_typeahead_answer(self, question: str, job: Job) -> Optional[str]:
        """
        Retrieves or generates an answer suitable for a typeahead field.

        Args:
            question (str): The sanitized question text.
            job (Job): The job object.

        Returns:
            Optional[str]: The answer string, or None on failure.
        """
        # Check cache first
        cached_answer = self.get_existing_answer(question, "typeahead")
        if cached_answer is not None:
            logger.debug(f"Using cached typeahead answer for '{question}'.")
            return cached_answer

        # Generate using LLM - use simple answer generation
        logger.info(f"No cached answer for typeahead '{question}'. Generating new answer.")
        try:
             # Ensure LLM processor is available
             if not hasattr(self.llm_processor, 'answer_question_simple'):
                 logger.error("LLMProcessor missing 'answer_question_simple' method.")
                 return self.FALLBACK_TYPEAHEAD_ANSWER

             # Typeahead often needs shorter, specific answers. Limit character count.
             # Adjust limit based on typical field content (e.g., location vs. skill)
             char_limit = 50 # Default limit for typeahead
             if "location" in question.lower() or "city" in question.lower():
                  char_limit = 80
             elif "skill" in question.lower():
                  char_limit = 40

             answer = self.llm_processor.answer_question_simple(question, char_limit)

             if answer is not None:
                 processed_answer = str(answer).strip()
                 # Basic filtering: remove common LLM refusals if needed
                 if "cannot answer" in processed_answer.lower() or "not applicable" in processed_answer.lower():
                      logger.warning(f"LLM could not provide specific answer for '{question}'. Using fallback.")
                      processed_answer = self.FALLBACK_TYPEAHEAD_ANSWER

                 logger.info(f"LLM generated typeahead answer for '{question}': '{processed_answer}'")
                 # Save the potentially filtered answer
                 self.save_answer(question, "typeahead", processed_answer)
                 return processed_answer
             else:
                  logger.warning(f"LLM returned None for typeahead '{question}'. Using fallback.")
                  self.save_answer(question, "typeahead", self.FALLBACK_TYPEAHEAD_ANSWER) # Save fallback
                  return self.FALLBACK_TYPEAHEAD_ANSWER

        except (LLMError, Exception) as e:
            logger.error(f"LLM failed for typeahead '{question}': {e}", exc_info=True)
            self.save_answer(question, "typeahead", self.FALLBACK_TYPEAHEAD_ANSWER) # Save fallback
            return self.FALLBACK_TYPEAHEAD_ANSWER


    def _fill_and_select(self, field: WebElement, answer: str, question_text: str) -> None:
        """
        Enters the answer text into the typeahead field and attempts to select
        the first matching suggestion from the list that appears.

        Args:
            field (WebElement): The typeahead input WebElement.
            answer (str): The text to enter.
            question_text (str): The associated question text (for logging).

        Raises:
            ElementNotInteractableException: If the field cannot be interacted with.
            TimeoutException: If suggestions do not appear in time.
            RuntimeError: If selection fails after all attempts.
            Exception: For other unexpected errors during the process.
        """
        max_attempts = 2 # Number of times to try the whole fill/select process
        for attempt in range(max_attempts):
            logger.debug(f"Typeahead fill/select attempt {attempt + 1} for '{question_text}'")
            try:
                # Clear and enter text using base method (handles basic errors)
                self.enter_text(field, answer)
                time.sleep(0.3) 
                logger.debug(f"Entered text '{answer}' into typeahead '{question_text}'. Waiting for suggestions...")

                # Wait a bit longer for suggestions to appear after typing
                time.sleep(1.5) # Adjust based on observed site behavior

                # --- Attempt to Select Suggestion ---
                suggestion_selected = False
                try:
                    if self._select_first_suggestion(field, answer):
                        suggestion_selected = True
                except (TimeoutException, NoSuchElementException):
                    logger.warning("Typeahead suggestions did not appear or were not found.")
                except Exception as select_err:
                     logger.warning(f"Error clicking suggestion: {select_err}. Will try keyboard fallback.")

                # --- Keyboard Fallback ---
                if not suggestion_selected:
                    logger.info("Using keyboard fallback (ARROW_DOWN + RETURN) for typeahead selection.")
                    try:
                         # Check if field still has focus (sometimes lost after typing/JS)
                         if self.driver.switch_to.active_element != field:
                             field.click() # Try to refocus
                             time.sleep(0.2)

                         field.send_keys(Keys.ARROW_DOWN)
                         time.sleep(0.5) # Wait for potential highlight/selection change
                         field.send_keys(Keys.RETURN)
                         time.sleep(0.5) # Wait for selection to process
                         logger.info(f"Keyboard fallback executed for typeahead '{question_text}'.")
                         suggestion_selected = True # Assume success if no error
                         # Verification after keyboard fallback is difficult

                         # Optional: Check if input value changed as expected (might be flaky)
                         # final_value = field.get_attribute('value')
                         # logger.debug(f"Value after keyboard fallback: '{final_value}'")
                         # if final_value.lower() != answer.lower():
                         #    Maybe selection picked a slightly different string? Still potentially okay.

                    except StaleElementReferenceException:
                         logger.error("Field became stale during keyboard fallback.")
                         raise # Re-raise stale exception to trigger outer retry or failure
                    except Exception as kb_err:
                        logger.error(f"Keyboard fallback failed for typeahead '{question_text}': {kb_err}", exc_info=False)
                        # Do not mark as selected, let the loop retry or fail

                # If successful on this attempt, break the loop
                if suggestion_selected:
                    logger.debug(f"Typeahead selection successful on attempt {attempt + 1}")
                    return # Exit the function successfully

                # If not selected, log and prepare for next attempt (if any)
                logger.warning(f"Typeahead selection failed on attempt {attempt + 1}.")
                if attempt < max_attempts - 1:
                     time.sleep(1) # Wait before retrying the whole process

            except StaleElementReferenceException:
                 logger.error(f"Field '{question_text}' became stale during fill/select attempt {attempt + 1}.")
                 if attempt == max_attempts - 1:
                     raise RuntimeError(f"Field '{question_text}' became stale after {max_attempts} attempts.") from None
                 time.sleep(1) # Wait before retrying
                 continue # Go to next attempt
            except Exception as e:
                logger.error(f"Unexpected error during _fill_and_select attempt {attempt + 1} for '{question_text}': {e}", exc_info=True)
                if attempt == max_attempts - 1:
                     raise RuntimeError(f"Unexpected error after {max_attempts} attempts for '{question_text}'") from e
                time.sleep(1) # Wait before retrying
                continue # Go to next attempt

        # If loop finishes without returning, all attempts failed
        logger.critical(f"Failed to fill and select typeahead '{question_text}' after {max_attempts} attempts.")
        if utils: utils.capture_screenshot(self.driver, f"typeahead_critical_failure_{question_text[:20]}")
        raise RuntimeError(f"Failed to select typeahead suggestion for '{question_text}' after {max_attempts} attempts.")


    def _select_first_suggestion(self, field: WebElement, entered_text: str) -> bool:
        """
        Finds the suggestion list and clicks the first valid option.

        Args:
            field (WebElement): The input field (used for context/focus).
            entered_text (str): The text that was typed into the field (for matching).

        Returns:
            bool: True if a suggestion was successfully clicked, False otherwise.

        Raises:
            TimeoutException: If the suggestion container or options do not appear.
            NoSuchElementException: If options appear but none are found with the expected structure.
        """
        logger.debug("Looking for typeahead suggestion container...")
        try:
            # Wait for the container of suggestions to become visible
            # Use a slightly longer wait here as suggestions might take time
            suggestion_wait = WebDriverWait(self.driver, 10) # Increased wait to 7 seconds
            container = suggestion_wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, self.SUGGESTION_CONTAINER_XPATH))
            )
            logger.debug("Suggestion container found.")

            # Wait for options within the container to be present *and visible*
            # Using visibility_of_all_elements_located might be better but can be slow/flaky
            # Stick with presence and filter visibility later.
            options = suggestion_wait.until(
                 EC.presence_of_all_elements_located((By.XPATH, self.SUGGESTION_OPTION_XPATH))
            )

            if not options:
                logger.warning("Suggestion container appeared, but no selectable options found within it (using presence check).")
                return False

            logger.debug(f"Found {len(options)} potential suggestion option(s).")

            # --- Select the Best Option ---
            best_option: Optional[WebElement] = None

            # Filter for visible options first
            visible_options = [opt for opt in options if opt.is_displayed()]
            if not visible_options:
                 logger.warning("No *visible* suggestion options found.")
                 return False

            logger.debug(f"Found {len(visible_options)} visible suggestion option(s).")

            # Try to find an exact (case-insensitive) match among visible options
            for option in visible_options:
                 option_text = option.text.strip()
                 if option_text.lower() == entered_text.lower():
                     best_option = option
                     logger.debug(f"Found exact match suggestion: '{option_text}'")
                     break

            # If no exact match, take the first visible option
            if not best_option:
                 best_option = visible_options[0]
                 logger.debug(f"Using first visible suggestion: '{best_option.text.strip()}'")


            # --- Click the Selected Option ---
            try:
                # Scroll into view and click using JS for robustness
                self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", best_option)
                time.sleep(0.2) # Brief pause after scroll
                # JS click can be more reliable than selenium's click for dynamic lists
                self.driver.execute_script("arguments[0].click();", best_option)
                logger.info(f"Clicked typeahead suggestion: '{best_option.text.strip()}'")
                time.sleep(0.5) # Allow time for selection to populate input field
                return True
            except StaleElementReferenceException:
                 logger.warning("Suggestion option became stale before it could be clicked.")
                 return False # Cannot click stale element
            except ElementNotInteractableException:
                 logger.warning("Suggestion option reported as not interactable. Trying keyboard fallback next.")
                 return False # Let the keyboard fallback handle it
            except Exception as click_err:
                logger.error(f"Failed to click suggestion option '{best_option.text.strip()}': {click_err}", exc_info=True)
                return False # Click failed

        except TimeoutException:
             logger.warning("Timed out waiting for typeahead suggestions container or options to appear/be present.")
             # Check if the value already matches (sometimes selection happens on blur/automatically)
             try:
                 current_value = field.get_attribute('value')
                 if current_value and entered_text and current_value.lower() == entered_text.lower():
                      logger.info("Typeahead value already matches entered text, assuming auto-selection occurred.")
                      return True
             except: pass # Ignore errors checking value
             return False # Suggestions didn't appear or match
        except NoSuchElementException: # Should be caught by WebDriverWait, but just in case
             logger.warning("Suggestion container or options not found via NoSuchElementException.")
             return False
        except Exception as e:
             logger.error(f"Unexpected error while selecting suggestion: {e}", exc_info=True)
             return False