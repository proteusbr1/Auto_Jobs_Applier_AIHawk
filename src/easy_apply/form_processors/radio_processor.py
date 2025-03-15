"""
Module for processing radio button form fields in LinkedIn Easy Apply forms.
"""
from typing import List
from loguru import logger
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC

from src.job import Job
from src.easy_apply.form_processors.base_processor import BaseProcessor

class RadioProcessor(BaseProcessor):
    """
    Processor for radio button form fields in LinkedIn Easy Apply forms.
    """
    
    def handle(self, section: WebElement, job: Job) -> bool:
        """
        Finds and handles radio button questions in the form section.
        
        Args:
            section (WebElement): The form section containing the radio buttons.
            job (Job): The job object.
            
        Returns:
            bool: True if radio buttons were found and handled, False otherwise.
        """
        logger.debug("Searching for radio questions")
        
        # Try to find radio buttons in the old structure first
        try:
            question_element = section.find_element(By.CLASS_NAME, self.selectors["old"]["form_element"])
            radios = question_element.find_elements(By.CLASS_NAME, self.selectors["old"]["radio_option"])
            
            if radios:
                logger.debug(f"Found {len(radios)} radio options")
                question_text = section.text.lower()
                options = [radio.text.lower() for radio in radios]
                logger.debug(f"Radio options: {options}")

                # Get answer (from storage or generate new one)
                answer = self._get_answer_for_question(question_text, "radio", options, job)
                
                # Select the radio button
                self._select_radio(radios, answer)
                return True
        except Exception as e:
            logger.debug(f"No radio buttons found in old structure: {e}")
        
        # Try to find radio buttons in the new structure
        try:
            # Look for radio buttons in the new structure
            # This is a placeholder - update with actual selectors when the new structure is known
            form_element = section.find_element(By.CLASS_NAME, self.selectors["new"]["form_element"])
            radios = form_element.find_elements(By.XPATH, ".//input[@type='radio']")
            
            if radios:
                logger.debug(f"Found {len(radios)} radio options in new structure")
                question_text = self.extract_question_text(section)
                
                # Get the labels for each radio option
                options = []
                for radio in radios:
                    label_id = radio.get_attribute("id")
                    if label_id:
                        label = section.find_element(By.XPATH, f"//label[@for='{label_id}']")
                        options.append(label.text.lower())
                
                logger.debug(f"Radio options in new structure: {options}")
                
                # Get answer (from storage or generate new one)
                answer = self._get_answer_for_question(question_text, "radio", options, job)
                
                # Select the radio button
                for i, option in enumerate(options):
                    if answer.lower() in option:
                        self.wait.until(EC.element_to_be_clickable(radios[i])).click()
                        logger.debug(f"Selected radio option '{option}' in new structure")
                        return True
                
                # If no match found, select the first option
                logger.warning(f"Answer '{answer}' not found in radio options; selecting the first option")
                self.wait.until(EC.element_to_be_clickable(radios[0])).click()
                logger.debug(f"Selected first radio option as fallback")
                return True
        except Exception as e:
            logger.debug(f"No radio buttons found in new structure: {e}")
        
        return False
    
    def _get_answer_for_question(self, question_text: str, question_type: str, 
                                options: List[str], job: Job) -> str:
        """
        Gets an answer for a question with options, either from storage or by generating a new one.
        
        Args:
            question_text (str): The question text.
            question_type (str): The question type.
            options (List[str]): The available options.
            job (Job): The job object.
            
        Returns:
            str: The answer.
        """
        # Check for existing answer
        existing_answer = self.get_existing_answer(question_text, question_type)
        if existing_answer:
            # For radios, verify the answer is still valid (contains any option text)
            if any(existing_answer.lower() in option for option in options):
                return existing_answer
            else:
                logger.warning(f"Existing answer '{existing_answer}' is not in available options")
                
        # Generate new answer
        answer = self.gpt_answerer.answer_question_from_options(question_text, options)
        
        # Save the answer
        self.save_answer(question_text, question_type, answer)
        
        logger.debug(f"Generated new answer: {answer}")
        return answer
    
    def _select_radio(self, radios: List[WebElement], answer: str) -> None:
        """
        Selects a radio button based on the answer.
        
        Args:
            radios (List[WebElement]): The list of radio button elements.
            answer (str): The answer text to select.
        """
        logger.debug(f"Selecting radio option: {answer}")
        
        # Try to find and click the matching radio option
        for radio in radios:
            if answer.lower() in radio.text.lower():
                try:
                    label = radio.find_element(By.TAG_NAME, self.selectors["common"]["label"])
                    self.wait.until(EC.element_to_be_clickable(label)).click()
                    logger.debug(f"Radio option '{answer}' selected")
                    return
                except Exception as e:
                    logger.warning(f"Failed to click radio option '{answer}': {e}")
                    continue
        
        # If no match found, select the last option as fallback
        logger.warning(f"Answer '{answer}' not found in radio options; selecting the last option")
        try:
            last_label = radios[-1].find_element(By.TAG_NAME, self.selectors["common"]["label"])
            self.wait.until(EC.element_to_be_clickable(last_label)).click()
            logger.debug("Last radio option selected as fallback")
        except Exception as e:
            logger.error(f"Failed to select last radio option: {e}", exc_info=True)
            raise
