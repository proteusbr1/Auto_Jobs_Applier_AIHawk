"""
Module for processing checkbox fields in LinkedIn Easy Apply forms.
"""
import time
from loguru import logger
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException

from src.easy_apply.form_processors.base_processor import BaseProcessor

class CheckboxProcessor(BaseProcessor):
    """
    Processor for checkbox fields in LinkedIn Easy Apply forms.
    """
    
    def _process_checkbox_with_retry(self, element: WebElement, checkbox: WebElement, 
                                   index: int, label_text: str) -> bool:
        """
        Process a single checkbox with retry mechanism for handling stale element references.
        
        Args:
            element (WebElement): The parent element containing the checkbox
            checkbox (WebElement): The checkbox element to process
            index (int): The index of the checkbox for logging
            label_text (str): The label text for logging
            
        Returns:
            bool: True if the checkbox was successfully processed, False otherwise
        """
        max_retries = 3
        for retry in range(max_retries):
            try:
                # If we're retrying, get a fresh reference to the checkbox
                if retry > 0:
                    logger.debug(f"Refreshing checkbox reference (retry {retry})")
                    try:
                        # Try to get a fresh reference using the standard selector
                        fresh_inputs = element.find_elements(By.XPATH, self.selectors["checkbox"]["standard"])
                        if index < len(fresh_inputs):
                            checkbox = fresh_inputs[index]
                        else:
                            # Try alternative selector methods
                            alt_inputs = []
                            try:
                                alt_inputs = element.find_elements(By.XPATH, self.selectors["checkbox"]["data_test"])
                            except Exception:
                                pass
                                
                            if not alt_inputs:
                                try:
                                    alt_inputs = element.find_elements(By.CLASS_NAME, self.selectors["checkbox"]["class_name"])
                                except Exception:
                                    pass
                            
                            if index < len(alt_inputs):
                                checkbox = alt_inputs[index]
                            else:
                                logger.warning(f"Cannot refresh checkbox {index} - no longer found")
                                return False
                        
                        # Brief pause to ensure the page is stable
                        time.sleep(0.5)
                    except Exception as refresh_error:
                        logger.warning(f"Error refreshing checkbox reference: {refresh_error}")
                        time.sleep(1)  # Wait longer on error
                        continue
                
                # Check if it's already selected
                try:
                    if checkbox.is_selected():
                        logger.debug(f"Checkbox {index} '{label_text}' is already checked")
                        return True
                except StaleElementReferenceException:
                    logger.debug("Stale element during is_selected check, retrying")
                    continue
                
                # Try multiple methods to click the checkbox
                click_methods = [
                    # Method 1: Direct click
                    lambda: self.wait.until(EC.element_to_be_clickable(checkbox)).click(),
                    
                    # Method 2: JavaScript click
                    lambda: self.driver.execute_script("arguments[0].click();", checkbox),
                    
                    # Method 3: Click the label instead
                    lambda: self.driver.execute_script(
                        "arguments[0].click();", 
                        checkbox.find_element(By.XPATH, self.selectors["checkbox"]["label_xpath"])
                    )
                ]
                
                # Try each method until one succeeds
                for method_index, click_method in enumerate(click_methods):
                    try:
                        click_method()
                        logger.debug(f"Clicked checkbox {index} (method {method_index+1}): '{label_text}'")
                        return True
                    except Exception as click_error:
                        logger.debug(f"Click method {method_index+1} failed: {click_error}")
                        continue
                
                # If we get here, all click methods failed
                logger.warning(f"All click methods failed for checkbox {index}")
                
            except StaleElementReferenceException:
                logger.debug(f"Stale element reference for checkbox {index}, retry {retry+1}")
                time.sleep(retry + 0.5)  # Increasing wait time with each retry
            except Exception as e:
                logger.warning(f"Error processing checkbox {index} (retry {retry}): {e}")
                time.sleep(retry + 0.5)  # Increasing wait time with each retry
        
        logger.warning(f"Failed to process checkbox {index} after {max_retries} retries")
        return False
    
    def handle(self, element: WebElement, job=None) -> bool:
        """
        Handles checkbox fields in the form.

        Args:
            element (WebElement): The form element containing the checkbox.
            job: The job object (optional, added for interface compatibility).

        Returns:
            bool: True if checkbox was found and clicked, False otherwise.
        """
        # Try multiple methods to find checkbox inputs
        checkbox_inputs = []
        
        # Method 1: Look for standard checkbox inputs
        checkbox_inputs = element.find_elements(By.XPATH, self.selectors["checkbox"]["standard"])
        
        # Method 2: Look for inputs with data-test attributes (new LinkedIn structure)
        if not checkbox_inputs:
            try:
                checkbox_inputs = element.find_elements(By.XPATH, self.selectors["checkbox"]["data_test"])
                logger.debug(f"Found {len(checkbox_inputs)} checkbox inputs using data-test attribute")
            except Exception as e:
                logger.debug(f"Error finding checkboxes by data-test attribute: {e}")
        
        # Method 3: Look for checkboxes by class name
        if not checkbox_inputs:
            try:
                checkbox_inputs = element.find_elements(By.CLASS_NAME, self.selectors["checkbox"]["class_name"])
                logger.debug(f"Found {len(checkbox_inputs)} checkbox inputs using class name")
            except Exception as e:
                logger.debug(f"Error finding checkboxes by class name: {e}")

        if not checkbox_inputs:
            logger.debug("No checkbox inputs found using any method")
            return False

        try:
            logger.debug(f"Found {len(checkbox_inputs)} checkbox inputs")
            
            # Get the fieldset element to check for language-related checkboxes
            fieldset_element = None
            try:
                # Try to find a parent fieldset
                parent = element
                for _ in range(5):  # Check up to 5 levels up
                    try:
                        parent = parent.find_element(By.XPATH, "./..")
                        fieldset = parent.find_elements(By.TAG_NAME, "fieldset")
                        if fieldset:
                            fieldset_element = fieldset[0]
                            break
                    except:
                        break
            except Exception as fieldset_error:
                logger.debug(f"Error finding parent fieldset: {fieldset_error}")
                        
            # Check if this is a required checkbox
            is_required = False

            # Try to find if there's a required label
            try:
                # Method 1: Check for required_label class
                required_labels = element.find_elements(By.CLASS_NAME, self.selectors["new"]["required_label"])
                
                # Method 2: Check for required in the parent element
                if not required_labels and fieldset_element:
                    required_labels = fieldset_element.find_elements(By.CLASS_NAME, self.selectors["new"]["required_label"])
                
                # Method 3: Look for "required" text in nearby spans
                if not required_labels:
                    required_spans = element.find_elements(By.XPATH, ".//span[contains(text(), 'Required')]")
                    if required_spans:
                        required_labels = required_spans
                
                if required_labels:
                    is_required = True
                    logger.debug("This is a required checkbox")
            except Exception as label_error:
                logger.debug(f"Error checking if checkbox is required: {label_error}")

            # Get the checkbox label text for logging
            label_text = "Unknown"
            try:
                # Try to get label from the element itself
                labels = element.find_elements(By.TAG_NAME, self.selectors["common"]["label"])
                if labels:
                    label_text = labels[0].text.strip()
                

            except Exception as label_error:
                logger.debug(f"Error getting checkbox label text: {label_error}")

            # If it's a required checkbox or contains certain keywords, check it
            should_check = is_required or any(
                term in label_text.lower()
                for term in ["agree", "terms", "policy", "consent", "accept", "confirm"]
            )

            if should_check:
                # Process each checkbox if there are multiple
                processed_count = 0
                for i, checkbox in enumerate(checkbox_inputs):
                    # Use our helper method with retry logic
                    success = self._process_checkbox_with_retry(element, checkbox, i, label_text)
                    if success:
                        processed_count += 1
                
                logger.debug(f"Successfully processed {processed_count} out of {len(checkbox_inputs)} checkboxes")
                
                return True
            else:
                logger.debug(f"Skipping optional checkbox: '{label_text}'")
                return True

        except Exception as e:
            logger.warning(f"Failed to process checkbox: {e}", exc_info=True)
            
            # Attempt emergency handling for required checkboxes with retry
            try:
                logger.debug("Attempting emergency checkbox handling")
                # Try to find any visible checkboxes that aren't disabled
                visible_checkboxes = element.find_elements(By.XPATH, f"{self.selectors['checkbox']['standard']} and not(@disabled)")
                if not visible_checkboxes:
                    # Try alternative selectors for emergency handling
                    try:
                        visible_checkboxes = element.find_elements(By.XPATH, self.selectors["checkbox"]["data_test"])
                    except:
                        pass
                
                if visible_checkboxes:
                    logger.debug(f"Found {len(visible_checkboxes)} visible checkboxes for emergency handling")
                    emergency_success = 0
                    for i, checkbox in enumerate(visible_checkboxes):
                        # Use our retry mechanism even in emergency mode
                        if self._process_checkbox_with_retry(element, checkbox, i, "Emergency checkbox"):
                            emergency_success += 1
                    
                    logger.debug(f"Emergency handling processed {emergency_success} out of {len(visible_checkboxes)} checkboxes")
                    if emergency_success > 0:
                        return True
            except Exception as emergency_error:
                logger.warning(f"Emergency checkbox handling failed: {emergency_error}")
            
            return False
