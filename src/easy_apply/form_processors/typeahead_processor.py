"""
Module for processing typeahead form fields in LinkedIn Easy Apply forms.
"""
import time
from loguru import logger
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC

from src.job import Job
from src.easy_apply.form_processors.base_processor import BaseProcessor

class TypeaheadProcessor(BaseProcessor):
    """
    Processor for typeahead form fields in LinkedIn Easy Apply forms.
    """
    
    def handle(self, section: WebElement, job: Job) -> bool:
        """
        Finds and handles typeahead questions in the form section.
        
        Args:
            section (WebElement): The form section containing the typeahead input.
            job (Job): The job object.
            
        Returns:
            bool: True if typeahead input was found and handled, False otherwise.
        """
        logger.debug("Searching for typeahead questions")

        # Locate the input field with role 'combobox'
        typeahead_inputs = section.find_elements(By.XPATH, self.selectors["common"]["typeahead"])
        if not typeahead_inputs:
            logger.debug("No typeahead field found")
            return False

        typeahead_input = typeahead_inputs[0]
        logger.debug("Typeahead field found")

        try:
            # Ensure the field is visible and clickable
            self.wait.until(EC.visibility_of(typeahead_input))
            self.wait.until(EC.element_to_be_clickable(typeahead_input))

            # Get the question text
            question_text = self.extract_question_text(section)
            logger.debug(f"Question text: {question_text}")

            # Get answer (from storage or generate new one)
            answer = self._get_typeahead_answer(question_text, job)
            
            # Enter and select from typeahead
            self._handle_typeahead_selection(typeahead_input, answer)
            return True

        except Exception as e:
            logger.error(f"Error handling typeahead question: {e}", exc_info=True)
            return False
    
    def _get_typeahead_answer(self, question_text: str, job: Job) -> str:
        """
        Gets an answer for a typeahead question, either from storage or by generating a new one.
        
        Args:
            question_text (str): The question text.
            job (Job): The job object.
            
        Returns:
            str: The answer.
        """
        # Check for existing answer
        existing_answer = self.get_existing_answer(question_text, "typeahead")
        if existing_answer:
            logger.debug(f"Using existing typeahead answer: {existing_answer}")
            return existing_answer
        
        # Generate new answer
        answer = self.gpt_answerer.answer_question_simple(question_text, job, 50)
        
        # Save the answer
        self.save_answer(question_text, "typeahead", answer)
        
        logger.debug(f"Generated new typeahead answer: {answer}")
        return answer
    
    def _handle_typeahead_selection(self, typeahead_input: WebElement, answer: str) -> None:
        """
        Enters text in a typeahead field and selects from the suggestions.
        
        Args:
            typeahead_input (WebElement): The typeahead input element.
            answer (str): The answer to enter.
        """
        # Enter the text
        logger.debug(f"Entering text in typeahead: {answer}")
        typeahead_input.clear()
        typeahead_input.send_keys(answer)
        time.sleep(1)  # Wait for suggestions to load

        # Try to select from suggestions
        try:
            self._select_from_typeahead_suggestions(typeahead_input)
        except Exception as e:
            logger.warning(f"Error selecting from typeahead suggestions: {e}", exc_info=True)
            # Try keyboard navigation as fallback
            logger.debug("Trying keyboard navigation for typeahead")
            typeahead_input.send_keys(Keys.ARROW_DOWN)
            typeahead_input.send_keys(Keys.RETURN)
            
        # Confirm selection
        selected_value = typeahead_input.get_attribute("value").strip()
        logger.debug(f"Selected value in typeahead: {selected_value}")
    
    def _select_from_typeahead_suggestions(self, typeahead_input: WebElement) -> None:
        """
        Selects the first suggestion from a typeahead dropdown.
        
        Args:
            typeahead_input (WebElement): The typeahead input element.
        """
        # Define XPaths for finding suggestions
        suggestions_container_xpath = ".//div[contains(@class, 'basic-typeahead__triggered-content')]"
        suggestions_xpath = ".//div[contains(@class, 'basic-typeahead__selectable')]"
        
        # Wait for suggestions container
        suggestions_container = self.wait.until(
            EC.visibility_of_element_located((By.XPATH, suggestions_container_xpath))
        )
        logger.debug("Suggestions container found")
        
        # Find all suggestions
        suggestions = suggestions_container.find_elements(By.XPATH, suggestions_xpath)
        if not suggestions:
            logger.warning("No suggestions found")
            raise ValueError("No suggestions found in typeahead")
            
        # Select the first suggestion
        first_suggestion = suggestions[0]
        logger.debug("Selecting first suggestion")
        self.driver.execute_script("arguments[0].scrollIntoView(true);", first_suggestion)
        first_suggestion.click()
        logger.debug("First suggestion selected")
