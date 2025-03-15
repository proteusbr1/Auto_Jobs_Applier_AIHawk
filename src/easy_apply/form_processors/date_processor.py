"""
Module for processing date form fields in LinkedIn Easy Apply forms.
"""
from datetime import datetime
from loguru import logger
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from src.job import Job
from src.easy_apply.form_processors.base_processor import BaseProcessor

class DateProcessor(BaseProcessor):
    """
    Processor for date form fields in LinkedIn Easy Apply forms.
    """
    
    def handle(self, section: WebElement, job: Job) -> bool:
        """
        Finds and handles date input questions in the form section.
        
        Args:
            section (WebElement): The form section containing the date input.
            job (Job): The job object.
            
        Returns:
            bool: True if date input was found and handled, False otherwise.
        """
        logger.debug("Searching for date questions")
        
        # Try to find date fields with different selectors
        date_fields = section.find_elements(By.XPATH, self.selectors["common"]["date_field"])
        if not date_fields:
            date_fields = section.find_elements(By.XPATH, self.selectors["common"]["date_field_alt"])
        
        if not date_fields:
            logger.debug("No date questions found")
            return False
            
        date_field = date_fields[0]
        question_text = self.extract_question_text(section)
        logger.debug(f"Found date question: {question_text}")
        
        # Get the appropriate answer
        answer_text = self._get_date_answer(question_text)
        
        # Enter the answer
        self.enter_text(date_field, answer_text)
        logger.debug(f"Entered date answer: {answer_text}")
        return True
    
    def _get_date_answer(self, question_text: str) -> str:
        """
        Gets a date answer, either from storage, current date, or by generating a new one.
        
        Args:
            question_text (str): The question text.
            
        Returns:
            str: The date answer in mm/dd/yyyy format.
        """
        # Check if it's asking for today's date
        if "today's date" in question_text.lower():
            answer_text = datetime.today().strftime("%m/%d/%Y")
            logger.debug(f"Using current date: {answer_text}")
            return answer_text
        
        # Check for existing answer
        existing_answer = self.get_existing_answer(question_text, "date")
        if existing_answer:
            logger.debug(f"Using existing date answer: {existing_answer}")
            return existing_answer
        
        # Generate new answer
        answer_date = self.gpt_answerer.answer_question_date(question_text)
        answer_text = answer_date.strftime("%m/%d/%Y")
        
        # Save the answer
        self.save_answer(question_text, "date", answer_text)
        
        logger.debug(f"Generated new date answer: {answer_text}")
        return answer_text
