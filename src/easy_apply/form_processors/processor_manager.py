"""
Module for managing form field processors in LinkedIn Easy Apply forms.
"""
from loguru import logger
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from src.job import Job
from src.llm.llm_manager import GPTAnswerer
from src.easy_apply.answer_storage import AnswerStorage
from src.easy_apply.form_processors.base_processor import BaseProcessor
from src.easy_apply.form_processors.textbox_processor import TextboxProcessor
from src.easy_apply.form_processors.dropdown_processor import DropdownProcessor
from src.easy_apply.form_processors.radio_processor import RadioProcessor
from src.easy_apply.form_processors.date_processor import DateProcessor
from src.easy_apply.form_processors.typeahead_processor import TypeaheadProcessor
from src.easy_apply.form_processors.tos_processor import TermsOfServiceProcessor

class FormProcessorManager:
    """
    Manager for form field processors in LinkedIn Easy Apply forms.
    """
    
    def __init__(self, driver: WebDriver, gpt_answerer: GPTAnswerer, answer_storage: AnswerStorage, wait_time: int = 10):
        """
        Initialize the FormProcessorManager with necessary components.
        
        Args:
            driver (WebDriver): The Selenium WebDriver instance.
            gpt_answerer (GPTAnswerer): The GPT answerer instance for generating answers.
            answer_storage (AnswerStorage): The answer storage instance for saving and retrieving answers.
            wait_time (int): The maximum time to wait for elements to appear.
        """
        self.driver = driver
        self.gpt_answerer = gpt_answerer
        self.answer_storage = answer_storage
        self.wait_time = wait_time
        
        # Initialize processors
        self._init_processors()
        
        logger.debug("FormProcessorManager initialized")
    
    def _init_processors(self) -> None:
        """
        Initialize all form field processors.
        """
        # Create processor instances
        self.processors = [
            TypeaheadProcessor(self.driver, self.gpt_answerer, self.answer_storage, self.wait_time),
            TermsOfServiceProcessor(self.driver, self.gpt_answerer, self.answer_storage, self.wait_time),
            RadioProcessor(self.driver, self.gpt_answerer, self.answer_storage, self.wait_time),
            TextboxProcessor(self.driver, self.gpt_answerer, self.answer_storage, self.wait_time),
            DateProcessor(self.driver, self.gpt_answerer, self.answer_storage, self.wait_time),
            DropdownProcessor(self.driver, self.gpt_answerer, self.answer_storage, self.wait_time)
        ]
        
        # Create a base processor for utility methods
        self.base_processor = BaseProcessor(self.driver, self.gpt_answerer, self.answer_storage, self.wait_time)
    
    def is_upload_field(self, element: WebElement) -> bool:
        """
        Checks if the element is an upload field.

        Args:
            element (WebElement): The WebElement to check.
            
        Returns:
            bool: True if it's an upload field, False otherwise.
        """
        return self.base_processor.is_upload_field(element)
    
    def process_form_section(self, section: WebElement, job: Job) -> bool:
        """
        Processes a single form section by trying each processor in sequence.
        
        Args:
            section (WebElement): The form section to process.
            job (Job): The job object.
            
        Returns:
            bool: True if the section was successfully processed, False otherwise.
        """
        logger.debug("Processing form section")
        
        # Get the current URL for error logging
        try:
            current_url = self.driver.current_url
        except:
            current_url = "unknown"
        
        # Try each processor in sequence until one succeeds
        for processor in self.processors:
            try:
                if processor.handle(section, job):
                    logger.debug(f"Section handled by {processor.__class__.__name__}")
                    return True
            except Exception as e:
                logger.warning(f"Error in {processor.__class__.__name__}: {e}", exc_info=True)
                logger.warning(f"Error occurred while processing job URL: {current_url}")
                
                # Try to capture a screenshot of the error
                try:
                    import src.utils as utils
                    utils.capture_screenshot(self.driver, f"error_in_{processor.__class__.__name__}")
                except Exception as screenshot_error:
                    logger.warning(f"Failed to capture screenshot: {screenshot_error}")
        
        logger.debug("No processor could handle this section")
        return False
