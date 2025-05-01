
# src/easy_apply/form_processors/processor_manager.py
"""
Manages the selection and execution of appropriate form field processors
for the LinkedIn Easy Apply workflow.
"""
from __future__ import annotations 
from typing import List, Type, Any, TYPE_CHECKING

from loguru import logger
from selenium.common import StaleElementReferenceException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

# Import BaseProcessor and specific processors
from .base_processor import BaseProcessor
from .textbox_processor import TextboxProcessor
from .dropdown_processor import DropdownProcessor
from .radio_processor import RadioProcessor
from .date_processor import DateProcessor
from .typeahead_processor import TypeaheadProcessor
from .tos_processor import TermsOfServiceProcessor
from .checkbox_processor import CheckboxProcessor

# Import utils for screenshot capability
try:
    import src.utils as utils
except ImportError:
    logger.warning("src.utils not found, screenshot capability on error disabled in FormProcessorManager.")
    utils = None # type: ignore

if TYPE_CHECKING:
    from src.job import Job 
    from src.llm import LLMProcessor
    from src.easy_apply.answer_storage import AnswerStorage
else:
    Job: Any = object          
    LLMProcessor: Any = object  
    AnswerStorage: Any = object

class FormProcessorManager:
    """
    Orchestrates the processing of form sections by delegating to specialized
    processors based on the type of input field detected.
    """

    def __init__(
        self,
        driver: WebDriver,
        llm_processor: LLMProcessor,
        answer_storage: AnswerStorage,
        wait_time: int = 10
    ) -> None:
        """
        Initializes the FormProcessorManager and its pool of field processors.

        Args:
            driver (WebDriver): The Selenium WebDriver instance.
            llm_processor (LLMProcessor): The LLM processor for generating answers.
            answer_storage (AnswerStorage): The storage for previous answers.
            wait_time (int): Default wait time for WebDriver waits.
        """
        self.driver: WebDriver = driver
        self.llm_processor: LLMProcessor = llm_processor
        self.answer_storage: AnswerStorage = answer_storage
        self.wait_time: int = wait_time

        # Base processor for utility methods like is_upload_field
        self.base_processor = BaseProcessor(driver, llm_processor, answer_storage, wait_time)

        # Initialize specific processors in a prioritized order
        self._processors: List[BaseProcessor] = self._initialize_processors()

        logger.info(f"FormProcessorManager initialized with {len(self._processors)} processors.")

    def _initialize_processors(self) -> List[BaseProcessor]:
        """Creates instances of all specific form field processors."""
        # The order determines the sequence in which processors attempt to handle a section.
        # Prioritize processors that handle more specific or potentially problematic fields first.
        processor_classes: List[Type[BaseProcessor]] = [
            # 1. TermsOfService/Required Checkboxes: Often block submission if missed.
            TermsOfServiceProcessor,
            CheckboxProcessor, # Handles general checkboxes, including required ones
            # 2. Radio Buttons: Common for single-choice required questions (e.g., authorization, language).
            RadioProcessor,
            # 3. Typeahead/Autocomplete: Can be complex, handle before standard text.
            TypeaheadProcessor,
            # 4. Date Inputs: Specific format required.
            DateProcessor,
            # 5. Dropdowns: Standard selection.
            DropdownProcessor,
             # 6. Textboxes/Textareas: Most general text input, handle last.
            TextboxProcessor,
        ]

        initialized_processors = []
        for processor_cls in processor_classes:
            try:
                instance = processor_cls(self.driver, self.llm_processor, self.answer_storage, self.wait_time)
                initialized_processors.append(instance)
                logger.debug(f"Initialized processor: {processor_cls.__name__}")
            except Exception as e:
                 logger.error(f"Failed to initialize processor {processor_cls.__name__}: {e}", exc_info=True)
                 # Decide if initialization failure is critical
                 # raise RuntimeError(f"Critical processor initialization failed: {processor_cls.__name__}") from e

        return initialized_processors

    def is_upload_field(self, element: WebElement) -> bool:
        """
        Checks if the given element contains a file upload input.

        Delegates the check to the BaseProcessor utility method.

        Args:
            element (WebElement): The WebElement to check.

        Returns:
            bool: True if it's identified as an upload field section, False otherwise.
        """
        return self.base_processor.is_upload_field(element)

    def process_form_section(self, section: WebElement, job: Job) -> bool:
        """
        Processes a given form section by iterating through the registered processors.

        Each processor attempts to handle the section based on the type of input field
        it's designed for. Processing stops once a processor successfully handles the section.

        Args:
            section (WebElement): The WebElement representing the form section to process.
            job (Job): The current job object, providing context for the LLM.

        Returns:
            bool: True if any processor successfully handled the section, False otherwise.
        """
        section_text_preview = section.text[:75].replace('\n', ' ') if section and hasattr(section, 'text') else "N/A"
        logger.debug(f"Processing form section starting with: '{section_text_preview}...'")

        try:
            # Iterate through the prioritized list of processors
            for processor in self._processors:
                processor_name = processor.__class__.__name__
                logger.trace(f"Attempting handle with: {processor_name}")
                try:
                    # The 'handle' method should return True if it successfully processed the section
                    if processor.handle(section, job):
                        logger.info(f"Section successfully handled by {processor_name}.")
                        return True
                    else:
                         logger.trace(f"{processor_name} did not handle this section.")
                except StaleElementReferenceException:
                    logger.error(f"Stale element reference encountered by {processor_name} while processing section '{section_text_preview}...'. Section processing aborted.")
                    # Capture screenshot for debugging stale elements
                    if utils: utils.capture_screenshot(self.driver, f"stale_element_{processor_name}")
                    return False # Abort processing this section if it becomes stale
                except Exception as e:
                    # Log errors from individual processors but continue trying others
                    logger.error(f"Error occurred within {processor_name} for section '{section_text_preview}...': {e}", exc_info=True)
                    # Capture screenshot on processor error
                    if utils: utils.capture_screenshot(self.driver, f"error_{processor_name}")
                    # Continue to the next processor, maybe the current one wasn't the right type

            # If no processor handled the section after trying all
            logger.warning(f"No suitable processor found for section starting with: '{section_text_preview}...'.")
            # Optional: Capture screenshot of unhandled sections
            # if utils: utils.capture_screenshot(self.driver, "unhandled_form_section")
            return False

        except Exception as e:
            # Catch unexpected errors during the management process itself
            logger.critical(f"Unexpected error in FormProcessorManager while processing section '{section_text_preview}...': {e}", exc_info=True)
            if utils: utils.capture_screenshot(self.driver, "form_processor_manager_critical_error")
            return False # Indicate failure if the manager itself fails