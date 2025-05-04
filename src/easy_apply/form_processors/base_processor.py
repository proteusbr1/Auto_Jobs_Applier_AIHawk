# src/easy_apply/form_processors/base_processor.py
"""
Base module defining the abstract structure and shared utilities for specific
form field processors used in the Easy Apply workflow.
"""

from __future__ import annotations                # ➊ postpone evaluation

import time
from typing import Any, Dict, Final, List, Optional, Tuple, TYPE_CHECKING

from loguru import logger
from selenium.common.exceptions import (
    ElementNotInteractableException, InvalidElementStateException,
    NoSuchElementException, StaleElementReferenceException, TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ---------------------------------------------------------------------------
# ➋ Type-only imports: available to the type-checker, ignored at runtime
# ---------------------------------------------------------------------------
if TYPE_CHECKING:
    from src.job import Job 
    from src.llm import LLMProcessor
    from src.easy_apply.answer_storage import AnswerStorage
else:
    Job: Any = object          
    LLMProcessor: Any = object  
    AnswerStorage: Any = object

# Import utils for screenshot capability, assuming it's available
try:
    import src.utils as utils
except ImportError:
    logger.warning("src.utils not found, screenshot capability on error disabled in BaseProcessor.")
    utils = None # type: ignore

# --- Constants ---
DEFAULT_WAIT_TIME: Final[int] = 10
TEXT_ENTRY_ERROR_FALLBACK: Final[str] = "N/A" # Fallback for text errors

# Centralized selectors dictionary
# Keys should be descriptive and map to common locator strategies (e.g., CSS class, XPath)
SELECTORS: Final[Dict[str, Dict[str, str]]] = {
    "new": { # Selectors potentially specific to newer LinkedIn UI versions
        "textarea": "artdeco-text-input__textarea", # Class for textareas
        "input": "artdeco-text-input--input",      # Class for standard text inputs
        "form_element": "fb-dash-form-element",    # Class for a form element container
        "select_container": "[data-test-text-entity-list-form-component]", # CSS Attribute selector for dropdowns
        "required_label": "fb-dash-form-element__label-title--is-required", # Class indicating a required field label
        "radio_fieldset": "[data-test-form-builder-radio-button-form-component='true']", # Attribute selector for radio button fieldset
        "radio_option_container": "div[data-test-text-selectable-option]", # XPath/CSS for radio option container
        "radio_input": "@data-test-text-selectable-option__input", # XPath attribute for radio input itself
        "radio_label": "@data-test-text-selectable-option__label"  # XPath attribute for radio label
    },
    "old": { # Selectors potentially specific to older LinkedIn UI versions
        "form_section": "jobs-easy-apply-form-section__grouping", # Class for a grouping of form elements
        "form_element": "jobs-easy-apply-form-element",         # Class for a single form element container
        "radio_option": "fb-text-selectable__option"           # Class for a radio button option
    },
    "common": { # Selectors likely applicable across versions
        "label": "label",                               # Standard HTML label tag
        "select": "select",                             # Standard HTML select tag
        "typeahead": ".//input[@role='combobox']",      # XPath for typeahead/autocomplete input
        "date_field": ".//input[@placeholder='mm/dd/yyyy']", # XPath for date input with specific placeholder
        "date_field_alt": ".//input[contains(@name, 'date') or contains(@id, 'date') or contains(@aria-label, 'date')]", # Alternative XPath for date inputs
        "file_input": ".//input[@type='file']"         # XPath for file input element
    },
    "checkbox": { # Selectors specifically for checkboxes
        "standard": ".//input[@type='checkbox']",       # XPath for standard checkbox input
        "data_test": ".//input[contains(@data-test-checkbox-input, 'true') or contains(@data-test-clickable-control-input, 'true')]", # XPath using data-test attributes
        "class_name": "fb-form-element__checkbox",      # Class name sometimes used for checkboxes
        "label_xpath": "./following-sibling::label | ./ancestor::div[1]//label" # XPath to find associated label relative to input
    }
}
# --- End Constants ---


class BaseProcessor:
    """
    Abstract base class for form field processors.

    Provides common functionalities like interacting with the WebDriver,
    managing timeouts, accessing the LLM for answers, handling answer storage,
    and common element interaction utilities.
    """

    def __init__(
        self,
        driver: WebDriver,
        llm_processor: LLMProcessor,
        answer_storage: AnswerStorage,
        wait_time: int = DEFAULT_WAIT_TIME
    ) -> None:
        """
        Initializes the BaseProcessor.

        Args:
            driver (WebDriver): The Selenium WebDriver instance.
            llm_processor (LLMProcessor): The LLM processor instance for generating answers.
                                          It's expected to contain the LoggingModelWrapper.
            answer_storage (AnswerStorage): Instance for saving and retrieving previously used answers.
            wait_time (int): Maximum time in seconds to wait for elements. Defaults to DEFAULT_WAIT_TIME.

        Raises:
            TypeError: If any input argument is not of the expected type.
        """
        if not isinstance(driver, WebDriver):
            raise TypeError("driver must be an instance of WebDriver")
        if not isinstance(llm_processor, LLMProcessor):
            # Allow placeholder during import errors but log warning
            if not hasattr(llm_processor, '__class__') or llm_processor.__class__.__name__ != 'LLMProcessor':
                 logger.warning("llm_processor might not be a valid LLMProcessor instance.")
            # raise TypeError("llm_processor must be an instance of LLMProcessor") # Be strict if needed
        if not isinstance(answer_storage, AnswerStorage):
             if not hasattr(answer_storage, '__class__') or answer_storage.__class__.__name__ != 'AnswerStorage':
                 logger.warning("answer_storage might not be a valid AnswerStorage instance.")
            # raise TypeError("answer_storage must be an instance of AnswerStorage") # Be strict if needed

        self.driver: WebDriver = driver
        self.llm_processor: LLMProcessor = llm_processor
        self.answer_storage: AnswerStorage = answer_storage
        self.selectors: Dict[str, Dict[str, str]] = SELECTORS # Make selectors accessible
        self.wait_time: int = wait_time 
        self.wait: WebDriverWait = WebDriverWait(self.driver, wait_time)
        

        logger.debug(f"{self.__class__.__name__} initialized with wait time {wait_time}s")

    def handle(self, element: WebElement, job: Any) -> bool:
        """
        Abstract method to handle a specific form element or section.

        Each concrete processor must implement this method to define how
        it interacts with its specific type of form field.

        Args:
            element (WebElement): The Selenium WebElement representing the form
                                  section or field to be processed.
            job (Any): The job object or relevant context (can be specific type).

        Returns:
            bool: True if the processor successfully handled the element, False otherwise.

        Raises:
            NotImplementedError: If the subclass does not implement this method.
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement the 'handle' method.")

    def is_upload_field(self, element: WebElement) -> bool:
        """
        Checks if the provided element contains a file input field.

        Args:
            element (WebElement): The WebElement container to check within.

        Returns:
            bool: True if a file input element (`<input type="file">`) is found
                  within the element, False otherwise.
        """
        try:
            # Use find_elements to avoid exception if not found
            file_inputs = element.find_elements(By.XPATH, self.selectors["common"]["file_input"])
            is_upload = bool(file_inputs)
            logger.trace(f"Element contains upload field: {is_upload}")
            return is_upload
        except StaleElementReferenceException:
            logger.warning("Stale element reference encountered while checking for upload field.")
            return False
        except Exception as e:
            logger.error(f"Error checking for upload field: {e}", exc_info=True)
            return False

    def extract_question_text(self, section: WebElement) -> str:
        """
        Extracts and **returns** the label/question associated with a form
        section.  
        If no text can be found, **raises RuntimeError** instead of merely
        logging a warning, so the caller can decide how to handle an
        unrecoverable situation.

        Args
        ----
        section : WebElement
            The container that holds the form element and its label.

        Returns
        -------
        str
            Sanitised question text.

        Raises
        ------
        RuntimeError
            When no question text can be extracted from the section.
        """
        logger.trace("Attempting to extract question text…")
        question_text: Optional[str] = None

        # ─── Strategy 1: visible <label> ────────────────────────────────────
        try:
            labels = section.find_elements(By.TAG_NAME, self.selectors["common"]["label"])
            visible_labels = [lbl.text.strip() for lbl in labels
                              if lbl.is_displayed() and lbl.text.strip()]
            if visible_labels:
                question_text = visible_labels[0]
                logger.trace(f"Found question via <label>: “{question_text}”")

                # If the label’s “for” points to an input, prefer that
                try:
                    input_id = section.find_element(
                        By.XPATH,
                        ".//input[@id]|.//textarea[@id]|.//select[@id]"
                    ).get_attribute("id")
                    if input_id:
                        linked = section.find_elements(By.XPATH, f".//label[@for='{input_id}']")
                        if linked and linked[0].text.strip():
                            question_text = linked[0].text.strip()
                            logger.trace(f"Refined via label[@for='{input_id}']: “{question_text}”")
                except NoSuchElementException:
                    pass  # no associated input id, keep first visible label
        except Exception as e:
            logger.warning(f"Error while using <label>: {e}", exc_info=False)

        # ─── Strategy 2: <legend> (fieldset titles) ────────────────────────
        if not question_text:
            try:
                legends = section.find_elements(By.TAG_NAME, "legend")
                visible_legends = [lg.text.strip() for lg in legends
                                   if lg.is_displayed() and lg.text.strip()]
                if visible_legends:
                    question_text = visible_legends[0]
                    logger.trace(f"Found question via <legend>: “{question_text}”")
            except Exception as e:
                logger.warning(f"Error while using <legend>: {e}", exc_info=False)


        # Strategy 3: Fallback to specific class names if label/legend fails
        # Add specific class names known to hold question text if needed
        # Example:
        # if not question_text:
        #     try:
        #         title_element = section.find_element(By.CLASS_NAME, "some-title-class")
        #         if title_element.is_displayed() and title_element.text.strip():
        #             question_text = title_element.text.strip()
        #             logger.trace(f"Found question via class 'some-title-class': '{question_text}'")
        #     except NoSuchElementException:
        #         pass
        #     except Exception as e:
        #         logger.warning(f"Error extracting text using class 'some-title-class': {e}", exc_info=False)


        # Strategy 4: Last resort - use the section's immediate text (can be noisy)
        # Be cautious with this, might grab irrelevant text. Only use if others fail.
        # if not question_text:
        #     try:
        #         # Get text directly from the section, excluding children's text might be complex
        #         section_text = section.text.strip()
        #         # Basic filtering to avoid grabbing just button text etc.
        #         if section_text and len(section_text) > 3 and not any(btn_txt in section_text for btn_txt in ["Next", "Submit", "Review"]):
        #             question_text = section_text.split('\n')[0] # Take first line as heuristic
        #             logger.trace(f"Found question via section text (fallback): '{question_text}'")
        #     except Exception as e:
        #         logger.warning(f"Error extracting text using section.text: {e}", exc_info=False)

        # Sanitize and return
        if question_text:
            sanitised = self.answer_storage.sanitize_text(question_text)
            logger.debug(f"Extracted question: “{sanitised}” (original: “{question_text[:50]}…”)")
            return sanitised

        # Nothing found → raise hard error
        msg = "Failed to extract question text from the form section."
        logger.error(msg)
        if utils:
            try:
                utils.capture_screenshot(
                    self.driver, f"question_extraction_failed_{self.__class__.__name__}"
                )
            except Exception as ss_err:
                logger.warning(f"Screenshot capture failed: {ss_err}", exc_info=False)
        raise RuntimeError(msg)

    def enter_text(self, element: WebElement, text: str) -> None:
        """
        Enters text into a specified form field element (input or textarea).

        Includes error handling, clearing the field, and JavaScript fallback.

        Args:
            element (WebElement): The target input or textarea WebElement.
            text (str): The text to be entered.
        """
        if not isinstance(text, str):
            original_type = type(text).__name__
            try:
                text = str(text)
                logger.warning(f"Input text was not a string (type: {original_type}), converted to: '{text[:50]}...'")
            except Exception as conversion_error:
                 logger.error(f"Failed to convert input text (type: {original_type}) to string: {conversion_error}")
                 text = TEXT_ENTRY_ERROR_FALLBACK # Use fallback if conversion fails

        logger.debug(f"Attempting to enter text: '{text[:50]}{'...' if len(text) > 50 else ''}'")

        try:
            # 1. Wait for element to be visible and enabled
            self.wait.until(EC.visibility_of(element))
            # Clickable check might fail for textareas sometimes, focus on enabled
            self.wait.until(lambda d: element.is_enabled())

            # 2. Clear the field (robustly)
            try:
                element.clear()
                # Add a check if clear worked, especially for buggy inputs
                if element.get_attribute('value') != '':
                    logger.warning("element.clear() did not fully clear the field. Trying JS clear.")
                    self.driver.execute_script("arguments[0].value = '';", element)
            except (InvalidElementStateException, ElementNotInteractableException) as clear_error:
                 logger.warning(f"Standard element.clear() failed: {clear_error}. Trying JS clear.")
                 try:
                     self.driver.execute_script("arguments[0].value = '';", element)
                 except Exception as js_clear_error:
                     logger.error(f"JS clear also failed: {js_clear_error}. Proceeding without guaranteed clear.")
            except StaleElementReferenceException:
                 logger.error("Stale element reference during clear. Cannot proceed with text entry.")
                 # Consider re-finding the element if critical, otherwise return/raise
                 return # Stop if element is stale

            # 3. Send keys
            element.send_keys(text)

            # 4. Verify input (optional but recommended)
            time.sleep(0.2) # Short pause for value update
            entered_value = element.get_attribute('value')
            if entered_value != text:
                 logger.warning(f"Verification failed. Expected: '{text[:50]}...', Got: '{entered_value[:50]}...'. Trying JS fallback.")
                 # Try JS fallback only if send_keys fails verification
                 self.driver.execute_script("arguments[0].value = arguments[1];", element, text)
                 time.sleep(0.2)
                 entered_value = element.get_attribute('value')
                 if entered_value == text:
                      logger.debug("Text entry successful using JavaScript fallback after verification failure.")
                 else:
                      logger.error("JavaScript fallback also failed verification.")
                      # Optionally raise an error here if text entry is critical
            else:
                logger.debug("Text entered and verified successfully.")

        except StaleElementReferenceException:
            logger.error("Stale element reference during text entry. Aborting entry for this field.")
            # Optionally capture screenshot
            if utils: utils.capture_screenshot(self.driver, f"stale_element_text_entry_{self.__class__.__name__}")
        except (TimeoutException, ElementNotInteractableException, WebDriverException) as e:
            logger.error(f"Failed to enter text using send_keys: {e.__class__.__name__}. Trying JS.", exc_info=False)
            # Try JS fallback immediately on these specific errors
            try:
                # Ensure element is scrolled into view for JS interaction
                self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", element)
                time.sleep(0.1)
                # Escape quotes in text for JS execution
                escaped_text = text.replace('"', '\\"').replace("'", "\\'")
                self.driver.execute_script(f"arguments[0].value = '{escaped_text}';", element)
                logger.info("Text entered using JavaScript fallback.")
                # Optionally verify again
                # time.sleep(0.2)
                # if element.get_attribute('value') != text:
                #     logger.error("JS fallback failed verification.")

            except Exception as js_error:
                logger.critical(f"Primary text entry and JS fallback failed: {js_error}", exc_info=True)
                # Capture screenshot on critical failure
                if utils: utils.capture_screenshot(self.driver, f"text_entry_critical_failure_{self.__class__.__name__}")
                # Depending on requirements, either raise an exception or continue
                # raise RuntimeError(f"Failed to enter text into field: {e}") from e
        except Exception as e:
             logger.critical(f"Unexpected error during text entry: {e}", exc_info=True)
             if utils: utils.capture_screenshot(self.driver, f"text_entry_unexpected_error_{self.__class__.__name__}")
             # raise RuntimeError(f"Unexpected error entering text: {e}") from e


    def get_existing_answer(self, question_text: str, question_type: str) -> Optional[str]:
        """
        Retrieves a previously stored answer for the given question and type.

        Args:
            question_text (str): The text of the question (should be sanitized).
            question_type (str): The type of the form field (e.g., 'textbox', 'dropdown').

        Returns:
            Optional[str]: The stored answer string if found, otherwise None.
        """
        logger.trace(f"Checking cache for answer to '{question_text}' (type: {question_type})")
        try:
            existing_answer = self.answer_storage.get_existing_answer(question_text, question_type)
            if existing_answer is not None: # Check explicitly for None, as "" can be a valid answer
                # Ensure the answer is a string before returning
                if not isinstance(existing_answer, str):
                     logger.warning(f"Cached answer for '{question_text}' is not string ({type(existing_answer)}), converting.")
                     existing_answer = str(existing_answer)

                logger.debug(f"Using cached answer for '{question_text}': '{existing_answer[:50]}...'")
                return existing_answer
            else:
                 logger.trace("No cached answer found.")
                 return None
        except Exception as e:
             logger.error(f"Error retrieving answer from storage for '{question_text}': {e}", exc_info=True)
             return None # Return None on storage error


    def save_answer(self, question_text: str, question_type: str, answer: str) -> None:
        """
        Saves the provided answer to the answer storage.

        Args:
            question_text (str): The text of the question (should be sanitized).
            question_type (str): The type of the form field.
            answer (str): The answer string to save.
        """
        # Ensure answer is string before saving
        if not isinstance(answer, str):
             original_type = type(answer).__name__
             try:
                 answer = str(answer)
                 logger.warning(f"Answer to save for '{question_text}' was not a string ({original_type}), converted.")
             except Exception as conversion_error:
                 logger.error(f"Failed to convert answer to string before saving for '{question_text}': {conversion_error}. Saving placeholder.")
                 answer = TEXT_ENTRY_ERROR_FALLBACK # Save fallback if conversion fails


        logger.trace(f"Saving answer for '{question_text}' (type: {question_type})")
        try:
            question_data = {
                "type": question_type,
                "question": question_text, # Assume already sanitized
                "answer": answer
            }
            self.answer_storage.save_question(question_data)
            logger.debug(f"Saved answer for '{question_text}': '{answer[:50]}...'")
        except Exception as e:
            logger.error(f"Error saving answer to storage for '{question_text}': {e}", exc_info=True)
            # Do not raise, allow process to continue