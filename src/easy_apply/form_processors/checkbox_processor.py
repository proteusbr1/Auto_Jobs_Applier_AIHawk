"""
Module for processing checkbox fields in LinkedIn Easy Apply forms.
"""
from loguru import logger
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC

from src.job import Job
from src.easy_apply.form_processors.base_processor import BaseProcessor

class CheckboxProcessor(BaseProcessor):
    """
    Processor for checkbox fields in LinkedIn Easy Apply forms.
    """
    
    def handle(self, element: WebElement, job: Job) -> bool:
        """
        Handles checkbox fields in the form.
        
        Args:
            element (WebElement): The form element containing the checkbox.
            job (Job): The job object (not used in this method but included for consistent interface).
            
        Returns:
            bool: True if checkbox was found and clicked, False otherwise.
        """
        # Look for checkbox inputs within the element
        checkbox_inputs = element.find_elements(By.XPATH, ".//input[@type='checkbox']")
        
        if not checkbox_inputs:
            return False
            
        try:
            logger.debug(f"Found {len(checkbox_inputs)} checkbox inputs")
            
            # Check if this is a required checkbox
            is_required = False
            
            # Try to find if there's a required label
            try:
                required_labels = element.find_elements(By.CLASS_NAME, self.selectors["new"]["required_label"])
                if required_labels:
                    is_required = True
                    logger.debug("This is a required checkbox")
            except Exception as label_error:
                logger.debug(f"Error checking if checkbox is required: {label_error}")
            
            # Get the checkbox label text for logging
            label_text = "Unknown"
            try:
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
                # Check if it's already checked
                if checkbox_inputs[0].is_selected():
                    logger.debug(f"Checkbox '{label_text}' is already checked")
                    return True
                
                # Click the checkbox
                self.wait.until(EC.element_to_be_clickable(checkbox_inputs[0])).click()
                logger.debug(f"Clicked checkbox: '{label_text}'")
                return True
            else:
                logger.debug(f"Skipping optional checkbox: '{label_text}'")
                return True
                
        except Exception as e:
            logger.warning(f"Failed to process checkbox: {e}", exc_info=True)
            return False
