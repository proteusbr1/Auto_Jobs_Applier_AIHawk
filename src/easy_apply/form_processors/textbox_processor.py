"""
Module for processing textbox form fields in LinkedIn Easy Apply forms.
"""
from typing import Tuple
from loguru import logger
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from src.job import Job
from src.easy_apply.form_processors.base_processor import BaseProcessor

class TextboxProcessor(BaseProcessor):
    """
    Processor for textbox form fields in LinkedIn Easy Apply forms.
    """
    
    def handle(self, section: WebElement, job: Job) -> bool:
        """
        Finds and handles textbox questions in the form section.
        
        Args:
            section (WebElement): The form section containing the textbox.
            job (Job): The job object.
            
        Returns:
            bool: True if textbox was found and handled, False otherwise.
        """
        logger.debug("Searching for textbox questions")
        
        # First try the new HTML structure
        if self._handle_new_textbox_structure(section, job):
            return True
            
        # Fall back to the old structure if new structure handling fails
        if self._handle_old_textbox_structure(section, job):
            return True
            
        logger.debug("No textbox questions found")
        return False
    
    def _handle_new_textbox_structure(self, section: WebElement, job: Job) -> bool:
        """
        Handles textbox questions in the new LinkedIn HTML structure.
        
        Args:
            section (WebElement): The form section containing the textbox.
            job (Job): The job object.
            
        Returns:
            bool: True if textbox was found and handled, False otherwise.
        """
        try:
            # Look for textareas in the new structure
            artdeco_textareas = section.find_elements(By.CLASS_NAME, self.selectors["new"]["textarea"])
            if artdeco_textareas:
                logger.debug("Found textarea in new artdeco structure")
                return self._process_artdeco_text_field(artdeco_textareas[0], section, job, is_textarea=True)
                
            # Look for inputs in the new structure
            artdeco_inputs = section.find_elements(By.CLASS_NAME, self.selectors["new"]["input"])
            if artdeco_inputs:
                logger.debug("Found input in new artdeco structure")
                return self._process_artdeco_text_field(artdeco_inputs[0], section, job, is_textarea=False)
                
            return False
        except Exception as e:
            logger.warning(f"Error handling new textbox structure: {e}", exc_info=True)
            return False
    
    def _process_artdeco_text_field(self, field: WebElement, section: WebElement, job: Job, is_textarea: bool) -> bool:
        """
        Processes a text field in the new artdeco structure.
        
        Args:
            field (WebElement): The text field element.
            section (WebElement): The form section containing the field.
            job (Job): The job object.
            is_textarea (bool): Whether the field is a textarea.
            
        Returns:
            bool: True if the field was successfully processed, False otherwise.
        """
        # Extract question text
        question_text, question_type = self._extract_question_info(field, section, is_textarea)
        logger.debug(f"Question: '{question_text}', Type: {question_type}")
        
        # Get the appropriate answer
        answer = self._get_answer_for_field(question_text, question_type, job)
        
        # Enter the answer
        self.enter_text(field, answer)
        logger.debug(f"Entered answer into the {'textarea' if is_textarea else 'input'}: {answer}")
        return True
    
    def _extract_question_info(self, field: WebElement, section: WebElement, is_textarea: bool) -> Tuple[str, str]:
        """
        Extracts the question text and determines the question type.
        
        Args:
            field (WebElement): The text field element.
            section (WebElement): The form section containing the field.
            is_textarea (bool): Whether the field is a textarea.
            
        Returns:
            Tuple[str, str]: The question text and question type.
        """
        # Find the label
        label_elements = section.find_elements(By.TAG_NAME, self.selectors["common"]["label"])
        question_text = label_elements[0].text.strip() if label_elements else "unknown"
        
        # Determine question type
        if is_textarea:
            # For textareas, check if it's a salary/compensation question
            is_salary = "salary" in question_text.lower() or "compensation" in question_text.lower()
            question_type = "numeric" if is_salary else "textbox"
        else:
            # For inputs, check if it's a numeric field
            field_type = field.get_attribute("type").lower()
            field_id = field.get_attribute("id").lower()
            is_numeric = "numeric" in field_id or field_type == "number"
            question_type = "numeric" if is_numeric else "textbox"
            
        return question_text, question_type
    
    def _handle_old_textbox_structure(self, section: WebElement, job: Job) -> bool:
        """
        Handles textbox questions in the old LinkedIn HTML structure.
        
        Args:
            section (WebElement): The form section containing the textbox.
            job (Job): The job object.
            
        Returns:
            bool: True if textbox was found and handled, False otherwise.
        """
        # Find all input and textarea elements
        text_fields = section.find_elements(By.TAG_NAME, "input") + section.find_elements(By.TAG_NAME, "textarea")
        
        if not text_fields:
            return False
            
        text_field = text_fields[0]
        label_elements = section.find_elements(By.TAG_NAME, self.selectors["common"]["label"])
        question_text = label_elements[0].text.lower().strip() if label_elements else "unknown"
        
        # Determine if the field is numeric
        field_type = text_field.get_attribute("type").lower()
        field_id = text_field.get_attribute("id").lower()
        is_numeric = "numeric" in field_id or field_type == "number"
        question_type = "numeric" if is_numeric else "textbox"
        
        # Check if it's a cover letter
        is_cover_letter = "cover letter" in question_text.lower()
        
        # Get the appropriate answer
        if is_cover_letter:
            answer = self.gpt_answerer.answer_question_simple(question_text, job, 1000)
            logger.debug("Generated cover letter")
        else:
            answer = self._get_answer_for_field(question_text, question_type, job)
        
        # Enter the answer
        self.enter_text(text_field, answer)
        logger.debug(f"Entered answer into the textbox: {answer}")
        return True
    
    def _get_answer_for_field(self, question_text: str, question_type: str, job: Job) -> str:
        """
        Gets an answer for a field, either from storage or by generating a new one.
        
        Args:
            question_text (str): The question text.
            question_type (str): The question type.
            job (Job): The job object.
            
        Returns:
            str: The answer.
        """
        # Check for existing answer
        existing_answer = self.get_existing_answer(question_text, question_type)
        if existing_answer:
            return existing_answer
        
        # Generate new answer
        if question_type == "numeric":
            answer = self.gpt_answerer.answer_question_numeric(question_text)
        else:
            answer = self.gpt_answerer.answer_question_simple(question_text, job=job)
            
        # Save the answer
        self.save_answer(question_text, question_type, answer)
        
        logger.debug(f"Generated new answer: {answer}")
        return answer
