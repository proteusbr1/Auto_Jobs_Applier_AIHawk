"""
Module for processing dropdown form fields in LinkedIn Easy Apply forms.
"""
from typing import List
from loguru import logger
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

from src.job import Job
from src.easy_apply.form_processors.base_processor import BaseProcessor

class DropdownProcessor(BaseProcessor):
    """
    Processor for dropdown form fields in LinkedIn Easy Apply forms.
    """
    
    def handle(self, section: WebElement, job: Job) -> bool:
        """
        Searches for and handles dropdown questions within a form section.

        Args:
            section (WebElement): The form section to be analyzed.
            job (Job): Object representing the current job posting.

        Returns:
            bool: True if a dropdown was found and handled successfully, False otherwise.
        """
        logger.debug("Starting search for dropdown questions in the section")

        # First try to find dropdowns in the new structure
        try:
            # Look for the select container in the new structure
            select_containers = section.find_elements(By.CSS_SELECTOR, f"[data-test-{self.selectors['new']['select_container']}]")
            if select_containers:
                logger.debug(f"Found {len(select_containers)} select containers in new structure")
                return self._handle_new_dropdown_structure(section, select_containers[0], job)
        except Exception as e:
            logger.debug(f"Error finding dropdowns in new structure: {e}")

        # Fall back to the old structure
        # Search for <select> elements in the section
        dropdowns = section.find_elements(By.TAG_NAME, self.selectors["common"]["select"])
        if not dropdowns:
            logger.debug("No dropdown found in this section")
            return False

        dropdown = dropdowns[0]
        logger.debug("Dropdown found in old structure")

        try:
            # Ensure the dropdown is visible and clickable
            self.wait.until(EC.visibility_of(dropdown))
            self.wait.until(EC.element_to_be_clickable(dropdown))

            # Extract available options from the dropdown
            select = Select(dropdown)
            options = [option.text.strip() for option in select.options]
            logger.debug(f"Dropdown options: {options}")

            # Extract the question text
            question_text = self.extract_question_text(section)
            logger.debug(f"Question text: {question_text}")

            # Get answer (from storage or generate new one)
            answer = self._get_answer_for_question(question_text, "dropdown", options, job)
            
            # Select the dropdown option
            self._select_dropdown_option(dropdown, answer)
            return True

        except Exception as e:
            logger.error(f"Error handling dropdown question: {e}", exc_info=True)
            return False
            
    def _handle_new_dropdown_structure(self, section: WebElement, select_container: WebElement, job: Job) -> bool:
        """
        Handles dropdown questions in the new LinkedIn HTML structure.
        
        Args:
            section (WebElement): The form section containing the dropdown.
            select_container (WebElement): The container element for the select.
            job (Job): The job object.
            
        Returns:
            bool: True if dropdown was found and handled, False otherwise.
        """
        try:
            # Find the select element within the container
            select_element = select_container.find_element(By.TAG_NAME, self.selectors["common"]["select"])
            logger.debug("Found select element in new structure")
            
            # Check if this is a required field
            is_required = False
            try:
                # Look for required label
                required_labels = select_container.find_elements(By.CLASS_NAME, self.selectors["new"]["required_label"])
                is_required = len(required_labels) > 0
                logger.debug(f"Field is required: {is_required}")
            except Exception as e:
                logger.debug(f"Error checking if field is required: {e}")
            
            # Extract question text
            label_elements = select_container.find_elements(By.TAG_NAME, self.selectors["common"]["label"])
            question_text = label_elements[0].text.strip() if label_elements else "unknown"
            logger.debug(f"Question text: {question_text}")
            
            # Extract available options
            select = Select(select_element)
            all_options = [option.text.strip() for option in select.options]
            
            # Filter out placeholder options like "Select an option"
            valid_options = [opt for opt in all_options if opt.lower() != "select an option"]
            logger.debug(f"Valid dropdown options: {valid_options}")
            
            if not valid_options:
                logger.warning("No valid options found in dropdown")
                return False
                
            # Get answer (from storage or generate new one)
            answer = self._get_answer_for_question(question_text, "dropdown", valid_options, job)
            
            # Select the dropdown option
            self._select_dropdown_option(select_element, answer)
            logger.debug(f"Selected option '{answer}' for question '{question_text}'")
            return True
            
        except Exception as e:
            logger.error(f"Error handling new dropdown structure: {e}", exc_info=True)
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
            # For dropdowns, verify the answer is still valid
            if existing_answer in options:
                return existing_answer
            else:
                logger.warning(f"Existing answer '{existing_answer}' is not in available options")
                
        # Generate new answer
        answer = self.gpt_answerer.answer_question_from_options(question_text, options)
        
        # Save the answer
        self.save_answer(question_text, question_type, answer)
        
        logger.debug(f"Generated new answer: {answer}")
        return answer
    
    def _select_dropdown_option(self, element: WebElement, text: str) -> None:
        """
        Selects an option from a dropdown.
        
        Args:
            element (WebElement): The dropdown element.
            text (str): The option text to select.
        """
        logger.debug(f"Selecting dropdown option: {text}")
        
        try:
            # Create Select object and get all options
            select = Select(element)
            options = [option.text.strip() for option in select.options]
            
            # Verify the option exists
            if text not in options:
                logger.error(f"Option '{text}' not found in dropdown. Available options: {options}")
                raise ValueError(f"Option '{text}' not found in dropdown")
                
            # Select the option
            select.select_by_visible_text(text)
            logger.debug(f"Dropdown option '{text}' selected successfully")
            
            # Wait for the selection to be updated
            selected_option = select.first_selected_option.text.strip()
            assert selected_option == text, f"Expected '{text}', but selected '{selected_option}'"
            logger.debug(f"Confirmation: '{selected_option}' was successfully selected")
            
            # Small delay to allow the page to update
            import time
            time.sleep(0.5)
            
        except AssertionError as ae:
            logger.error(f"AssertionError: {ae}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Failed to select dropdown option '{text}': {e}", exc_info=True)
            raise
