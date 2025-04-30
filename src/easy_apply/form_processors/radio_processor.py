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
        
        # Try to find radio buttons in the new structure (2025)
        try:
            # Look for radio buttons in the new structure
            # First try to find the fieldset which contains the radio buttons
            fieldset = section.find_element(By.XPATH, f".//fieldset[@{self.selectors['new']['radio_fieldset']}='true']")
            
            if fieldset:
                logger.debug("Found fieldset for radio buttons in new structure")
                
                # Extract the question text from the legend
                legend = fieldset.find_element(By.TAG_NAME, "legend")
                question_text = legend.text.strip()
                logger.debug(f"Question text from legend: {question_text}")
                
                # Find all radio options using the data-test attribute for stability
                radio_options = fieldset.find_elements(By.XPATH, f".//{self.selectors['new']['radio_option_container']}")
                
                if radio_options:
                    logger.debug(f"Found {len(radio_options)} radio options in new structure using data-test attribute")
                    
                    # Get the labels and inputs for each radio option
                    options = []
                    radio_inputs = []
                    
                    for option in radio_options:
                        try:
                            # Find the input element using its specific data-test attribute
                            input_elem = option.find_element(By.XPATH, f".//input[@{self.selectors['new']['radio_input']}]")
                            radio_inputs.append(input_elem)
                            
                            # Find the label element using its specific data-test attribute
                            label_elem = option.find_element(By.XPATH, f".//label[@{self.selectors['new']['radio_label']}]")
                            option_text = label_elem.text.strip().lower()
                            options.append(option_text)
                            
                            logger.debug(f"Found radio option: {option_text}")
                        except Exception as e:
                            logger.warning(f"Error extracting radio option: {e}")
                    
                    logger.debug(f"Radio options in new structure: {options}")
                    
                    # Get answer (from storage or generate new one)
                    answer = self._get_answer_for_question(question_text, "radio", options, job)
                    
                    # Select the radio button
                    selected = False
                    for i, option in enumerate(options):
                        if answer.lower() in option:
                            try:
                                # Try JavaScript click on the input element
                                self.driver.execute_script("arguments[0].click();", radio_inputs[i])
                                logger.debug(f"Selected radio option '{option}' using JavaScript click")
                                selected = True
                                return True
                            except Exception as js_click_error:
                                logger.warning(f"Failed to click radio input with JavaScript: {js_click_error}")
                                try:
                                    # Try clicking the label instead, finding it by its specific data-test attribute
                                    label = radio_options[i].find_element(By.XPATH, f".//label[@{self.selectors['new']['radio_label']}]")
                                    self.driver.execute_script("arguments[0].click();", label)
                                    logger.debug(f"Selected radio option '{option}' by clicking label with JavaScript")
                                    selected = True
                                    return True
                                except Exception as label_click_error:
                                    logger.warning(f"Failed to click radio label with JavaScript: {label_click_error}")
                    
                    # If no match found or clicking failed, select the first option
                    if not selected:
                        logger.warning(f"Answer '{answer}' not found in radio options or clicking failed; selecting the first option")
                        try:
                            # Try JavaScript click on the first input
                            self.driver.execute_script("arguments[0].click();", radio_inputs[0])
                            logger.debug(f"Selected first radio option using JavaScript click as fallback")
                            return True
                        except Exception as first_js_click_error:
                            logger.warning(f"Failed to click first radio input with JavaScript: {first_js_click_error}")
                            try:
                                # Try clicking the first label with JavaScript, finding it by its specific data-test attribute
                                first_label = radio_options[0].find_element(By.XPATH, f".//label[@{self.selectors['new']['radio_label']}]")
                                self.driver.execute_script("arguments[0].click();", first_label)
                                logger.debug(f"Selected first radio option by clicking label with JavaScript as fallback")
                                return True
                            except Exception as first_label_click_error:
                                logger.error(f"Failed to click first radio label with JavaScript: {first_label_click_error}")
                                
                                # Last resort: try to use ActionChains
                                try:
                                    from selenium.webdriver.common.action_chains import ActionChains
                                    actions = ActionChains(self.driver)
                                    actions.move_to_element(radio_inputs[0]).click().perform()
                                    logger.debug("Selected first radio option using ActionChains as last resort")
                                    return True
                                except Exception as action_error:
                                    logger.error(f"Failed to click using ActionChains: {action_error}")
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
