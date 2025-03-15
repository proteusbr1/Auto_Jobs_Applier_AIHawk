"""
Base module for form field processors with common functionality.
"""
import time
from typing import List, Optional, Tuple, Dict, Any
from loguru import logger
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.job import Job
from src.llm.llm_manager import GPTAnswerer
from src.easy_apply.answer_storage import AnswerStorage

# HTML class names and selectors for different form elements
# Centralizing these makes it easier to update when LinkedIn changes their HTML structure
SELECTORS = {
    # New LinkedIn structure (2025)
    "new": {
        "textarea": "artdeco-text-input__textarea",
        "input": "artdeco-text-input--input",
        "form_section": "PhUvDQfCdKEziUOXPXmpuBzOwdFzCzynpE",
        "form_element": "fb-dash-form-element",
        "select_container": "text-entity-list-form-component",
        "required_label": "fb-dash-form-element__label-title--is-required"
    },
    # Old LinkedIn structure
    "old": {
        "form_section": "jobs-easy-apply-form-section__grouping",
        "form_element": "jobs-easy-apply-form-element",
        "radio_option": "fb-text-selectable__option"
    },
    # Common selectors
    "common": {
        "label": "label",
        "select": "select",
        "typeahead": ".//input[@role='combobox']",
        "date_field": ".//input[@placeholder='mm/dd/yyyy']",
        "date_field_alt": ".//input[@name='artdeco-date']",
        "file_input": ".//input[@type='file']"
    }
}

class BaseProcessor:
    """
    Base class for form field processors with common functionality.
    """
    
    def __init__(self, driver: WebDriver, gpt_answerer: GPTAnswerer, answer_storage: AnswerStorage, wait_time: int = 10):
        """
        Initialize the BaseProcessor with common dependencies.
        
        Args:
            driver (WebDriver): The Selenium WebDriver instance.
            gpt_answerer (GPTAnswerer): The GPT answerer instance for generating answers.
            answer_storage (AnswerStorage): The answer storage instance for saving and retrieving answers.
            wait_time (int): The maximum time to wait for elements to appear.
        """
        self.driver = driver
        self.wait = WebDriverWait(self.driver, wait_time)
        self.gpt_answerer = gpt_answerer
        self.answer_storage = answer_storage
        self.selectors = SELECTORS
        logger.debug(f"{self.__class__.__name__} initialized")
    
    def is_upload_field(self, element: WebElement) -> bool:
        """
        Checks if the element is an upload field.

        Args:
            element (WebElement): The WebElement to check.
            
        Returns:
            bool: True if it's an upload field, False otherwise.
        """
        is_upload = bool(element.find_elements(By.XPATH, self.selectors["common"]["file_input"]))
        logger.debug(f"Element is upload field: {is_upload}")
        return is_upload
    
    def extract_question_text(self, section: WebElement) -> str:
        """
        Extracts the question text from a specific section of the form.

        Args:
            section (WebElement): The form section where the question is located.

        Returns:
            str: The question text or 'unknown' if extraction fails.
        """
        # Try multiple methods to extract the question text
        extraction_methods = [
            # Method 1: Get text from label elements
            lambda s: next((e.text.strip() for e in s.find_elements(
                By.TAG_NAME, self.selectors["common"]["label"]) if e.text.strip()), None),
                
            # Method 2: Get text from specific span elements
            lambda s: next((e.text.strip() for e in s.find_elements(
                By.CLASS_NAME, "jobs-easy-apply-form-section__group-title") if e.text.strip()), None),
                
            # Method 3: Use the section's full text
            lambda s: s.text.strip() if s.text.strip() else None
        ]
        
        # Try each method in order until one succeeds
        for method in extraction_methods:
            result = method(section)
            if result:
                return result
        
        # If all methods fail, return 'unknown'
        logger.warning("Failed to extract question text from section")
        return 'unknown'
    
    def enter_text(self, element: WebElement, text: str) -> None:
        """
        Enters text into a form field.
        
        Args:
            element (WebElement): The form field element.
            text (str): The text to enter.
        """
        try:
            self.wait.until(EC.element_to_be_clickable(element))
            element.clear()
            element.send_keys(text)
            logger.debug(f"Text entered successfully: {text[:20]}{'...' if len(text) > 20 else ''}")
        except Exception as e:
            logger.error(f"Failed to enter text: {e}", exc_info=True)
            raise
    
    def get_existing_answer(self, question_text: str, question_type: str) -> Optional[str]:
        """
        Gets an existing answer from storage if available.
        
        Args:
            question_text (str): The question text.
            question_type (str): The question type.
            
        Returns:
            Optional[str]: The existing answer or None if not found.
        """
        existing_answer = self.answer_storage.get_existing_answer(question_text, question_type)
        if existing_answer:
            logger.debug(f"Using existing answer: {existing_answer}")
            return existing_answer
        return None
    
    def save_answer(self, question_text: str, question_type: str, answer: str) -> None:
        """
        Saves an answer to storage.
        
        Args:
            question_text (str): The question text.
            question_type (str): The question type.
            answer (str): The answer to save.
        """
        self.answer_storage.save_question({
            "type": question_type, 
            "question": question_text, 
            "answer": answer
        })
        logger.debug(f"Saved answer for '{question_text}': {answer[:20]}{'...' if len(answer) > 20 else ''}")
