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
    
    # Blacklist of questions that should always generate new answers
    # These questions will bypass the answer storage lookup
    BLACKLISTED_QUESTIONS = [
        "headline",
        "cover letter",
        "why are you interested in this position",
        "why do you want to work here",
        "why are you a good fit for this role",
        "tell us about yourself",
        "what makes you unique",
        "what are your strengths",
        "what are your weaknesses"
    ]
    
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
            # Check if selectors is a dictionary and has the expected structure
            if not isinstance(self.selectors, dict) or "new" not in self.selectors or not isinstance(self.selectors["new"], dict):
                logger.warning("Invalid selectors structure in TextboxProcessor")
                return False
                
            # Look for textareas in the new structure
            textarea_selector = self.selectors["new"].get("textarea")
            if textarea_selector:
                artdeco_textareas = section.find_elements(By.CLASS_NAME, textarea_selector)
                if artdeco_textareas:
                    logger.debug("Found textarea in new artdeco structure")
                    return self._process_artdeco_text_field(artdeco_textareas[0], section, job, is_textarea=True)
                
            # Look for inputs in the new structure
            input_selector = self.selectors["new"].get("input")
            if input_selector:
                artdeco_inputs = section.find_elements(By.CLASS_NAME, input_selector)
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
        try:
            # Check if selectors is a dictionary and has the expected structure
            if not isinstance(self.selectors, dict) or "common" not in self.selectors or not isinstance(self.selectors["common"], dict):
                logger.warning("Invalid selectors structure in _extract_question_info")
                return "unknown", "textbox"
                
            # Find the label
            label_selector = self.selectors["common"].get("label")
            if not label_selector:
                logger.warning("Label selector not found in common selectors")
                question_text = "unknown"
            else:
                label_elements = section.find_elements(By.TAG_NAME, label_selector)
                question_text = label_elements[0].text.strip() if label_elements and len(label_elements) > 0 else "unknown"
            
            # Determine question type
            if is_textarea:
                # For textareas, check if it's a salary/compensation question
                is_salary = "salary" in question_text.lower() or "compensation" in question_text.lower()
                question_type = "numeric" if is_salary else "textbox"
            else:
                # For inputs, check if it's a numeric field
                try:
                    field_type = field.get_attribute("type")
                    field_type = field_type.lower() if field_type else ""
                    
                    field_id = field.get_attribute("id")
                    field_id = field_id.lower() if field_id else ""
                    
                    is_numeric = "numeric" in field_id or field_type == "number"
                    question_type = "numeric" if is_numeric else "textbox"
                except Exception as e:
                    logger.warning(f"Error determining field type: {e}")
                    question_type = "textbox"  # Default to textbox if we can't determine
                
            return question_text, question_type
        except Exception as e:
            logger.warning(f"Error in _extract_question_info: {e}", exc_info=True)
            return "unknown", "textbox"  # Return default values on error
    
    def _handle_old_textbox_structure(self, section: WebElement, job: Job) -> bool:
        """
        Handles textbox questions in the old LinkedIn HTML structure.
        
        Args:
            section (WebElement): The form section containing the textbox.
            job (Job): The job object.
            
        Returns:
            bool: True if textbox was found and handled, False otherwise.
        """
        try:
            # Find all input and textarea elements
            text_fields = section.find_elements(By.TAG_NAME, "input") + section.find_elements(By.TAG_NAME, "textarea")
            
            if not text_fields:
                return False
                
            text_field = text_fields[0]
            
            # Check if selectors is a dictionary and has the expected structure
            if not isinstance(self.selectors, dict) or "common" not in self.selectors or not isinstance(self.selectors["common"], dict):
                logger.warning("Invalid selectors structure in _handle_old_textbox_structure")
                question_text = "unknown"
            else:
                label_selector = self.selectors["common"].get("label")
                if not label_selector:
                    logger.warning("Label selector not found in common selectors")
                    question_text = "unknown"
                else:
                    label_elements = section.find_elements(By.TAG_NAME, label_selector)
                    question_text = label_elements[0].text.lower().strip() if label_elements and len(label_elements) > 0 else "unknown"
            
            # Determine if the field is numeric
            try:
                field_type = text_field.get_attribute("type")
                field_type = field_type.lower() if field_type else ""
                
                field_id = text_field.get_attribute("id")
                field_id = field_id.lower() if field_id else ""
                
                is_numeric = "numeric" in field_id or field_type == "number"
                question_type = "numeric" if is_numeric else "textbox"
            except Exception as e:
                logger.warning(f"Error determining field type: {e}")
                question_type = "textbox"  # Default to textbox if we can't determine
            
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
        except Exception as e:
            logger.warning(f"Error in _handle_old_textbox_structure: {e}", exc_info=True)
            return False
    
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
        # Check if the question is in the blacklist
        sanitized_question = question_text.lower().strip()
        is_blacklisted = any(blacklisted_question in sanitized_question for blacklisted_question in self.BLACKLISTED_QUESTIONS)
        
        if is_blacklisted:
            logger.debug(f"Question '{sanitized_question}' is blacklisted. Generating new answer.")
        else:
            # Check for existing answer if not blacklisted
            existing_answer = self.get_existing_answer(question_text, question_type)
            if existing_answer:
                logger.debug(f"Using existing answer for '{sanitized_question}'")
                return existing_answer
        
        # Generate new answer
        try:
            if question_type == "numeric":
                answer = self.gpt_answerer.answer_question_numeric(question_text)
                # Ensure the answer is a string
                if not isinstance(answer, str):
                    answer = str(answer)
                    logger.debug(f"Converted numeric answer to string: {answer}")
            else:
                answer = self.gpt_answerer.answer_question_simple(question_text, job=job)
                
            # Save the answer
            self.save_answer(question_text, question_type, answer)
            
            logger.debug(f"Generated new answer: {answer}")
            return answer
        except Exception as e:
            logger.error(f"Error generating answer for '{question_text}': {e}", exc_info=True)
            # Return a safe default value
            if question_type == "numeric":
                return "0"
            else:
                return "N/A"
