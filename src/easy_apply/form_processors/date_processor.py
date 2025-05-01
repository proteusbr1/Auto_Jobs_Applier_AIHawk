# src/easy_apply/form_processors/date_processor.py
"""
Module for processing date input form fields (e.g., start date, availability date)
within LinkedIn Easy Apply forms.
"""
from __future__ import annotations 
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from loguru import logger
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

# Assuming BaseProcessor correctly imports dependencies
from .base_processor import BaseProcessor
# Assuming Job object definition is available

if TYPE_CHECKING:
    from src.job import Job 
else:
    Job: Any = object          

class DateProcessor(BaseProcessor):
    """
    Processes date input fields, typically expecting `mm/dd/yyyy` format.

    Retrieves answers from storage or generates them using the LLM, handling
    special cases like "today's date".
    """

    # Common keywords indicating a request for the current date
    TODAY_DATE_KEYWORDS: List[str] = ["today", "current date"]

    def handle(self, section: WebElement, job: Job) -> bool:
        """
        Finds and handles date input fields within the given form section.

        Args:
            section (WebElement): The WebElement representing the form section
                                  containing the date input.
            job (Job): The job object (used for context if LLM is needed).

        Returns:
            bool: True if a date input field was found and successfully handled,
                  False otherwise.
        """
        logger.debug("DateProcessor: Scanning section for date fields...")

        date_field: Optional[WebElement] = None
        selector_used: Optional[str] = None

        # Try finding date fields using different strategies defined in base selectors
        date_selectors = [
            self.selectors["common"]["date_field"],
            self.selectors["common"]["date_field_alt"]
        ]

        for selector in date_selectors:
            try:
                # Use find_elements to avoid exception if not found
                potential_fields = section.find_elements(By.XPATH, selector)
                if potential_fields:
                    # Prioritize visible and enabled fields
                    for field in potential_fields:
                        if field.is_displayed() and field.is_enabled():
                            date_field = field
                            selector_used = selector
                            logger.debug(f"Found active date field using selector: {selector}")
                            break # Use the first active field found
                    if date_field: break # Stop searching selectors if an active field is found
            except StaleElementReferenceException:
                 logger.warning(f"Stale element reference while searching for date field with selector: {selector}")
                 continue # Try next selector
            except Exception as e:
                logger.warning(f"Error searching for date field with selector {selector}: {e}", exc_info=False)
                continue # Try next selector

        if not date_field:
            logger.trace("No active date field found in this section.")
            return False

        # Extract question text associated with the field
        question_text = self.extract_question_text(section)
        logger.debug(f"Date question identified: '{question_text}'")

        # Get the appropriate date answer (handles cache, LLM, 'today')
        answer_text = self._get_date_answer(question_text)

        if not answer_text:
             logger.error(f"Could not determine a valid date answer for question: '{question_text}'. Skipping field.")
             return False # Cannot proceed without an answer


        # Enter the date answer into the field
        try:
            self.enter_text(date_field, answer_text)
            logger.info(f"Entered date '{answer_text}' for question '{question_text}'.")
            return True
        except Exception as e:
             logger.error(f"Failed to enter date '{answer_text}' into field for question '{question_text}': {e}", exc_info=True)
             # Consider if failure to enter date should stop the process
             return False


    def _get_date_answer(self, question_text: str) -> Optional[str]:
        """
        Determines the appropriate date answer string in 'MM/DD/YYYY' format.

        Checks for "today's date" requests, looks in answer storage, and
        falls back to generating a date using the LLMProcessor.

        Args:
            question_text (str): The (sanitized) question text associated with the date field.

        Returns:
            Optional[str]: The date answer formatted as 'MM/DD/YYYY', or None if
                           an answer cannot be determined.
        """
        question_lower = question_text.lower()

        # Handle requests for today's date
        if any(keyword in question_lower for keyword in self.TODAY_DATE_KEYWORDS):
            try:
                today_date_str = datetime.today().strftime("%m/%d/%Y")
                logger.debug(f"Using current date for '{question_text}': {today_date_str}")
                return today_date_str
            except Exception as e:
                 logger.error(f"Error formatting today's date: {e}", exc_info=True)
                 return None # Cannot provide today's date if formatting fails


        # Check cache (answer storage)
        # Assumes question_text is already sanitized by extract_question_text
        cached_answer = self.get_existing_answer(question_text, "date")
        if cached_answer:
            # Optional: Validate cached date format if necessary
            try:
                 datetime.strptime(cached_answer, "%m/%d/%Y") # Validate format
                 logger.debug(f"Using cached date answer for '{question_text}': {cached_answer}")
                 return cached_answer
            except ValueError:
                 logger.warning(f"Cached date answer '{cached_answer}' for '{question_text}' has invalid format. Ignoring cache.")
            except Exception as e:
                logger.error(f"Error validating cached date '{cached_answer}': {e}. Ignoring cache.")


        # Generate date using LLM as fallback
        logger.debug(f"No valid cached answer for '{question_text}'. Querying LLM...")
        try:
            # Ensure LLM processor is available
            if not hasattr(self.llm_processor, 'answer_question_date'):
                 logger.error("LLMProcessor does not have 'answer_question_date' method.")
                 return None

            answer_datetime: Optional[datetime] = self.llm_processor.answer_question_date(question_text)

            if answer_datetime:
                generated_date_str = answer_datetime.strftime("%m/%d/%Y")
                logger.info(f"LLM generated date for '{question_text}': {generated_date_str}")
                # Save the newly generated answer
                self.save_answer(question_text, "date", generated_date_str)
                return generated_date_str
            else:
                logger.error(f"LLM failed to generate a date answer for question: '{question_text}'")
                return None # LLM failed to provide an answer

        except Exception as e:
            logger.error(f"Error generating date answer via LLM for '{question_text}': {e}", exc_info=True)
            return None # Return None on LLM error