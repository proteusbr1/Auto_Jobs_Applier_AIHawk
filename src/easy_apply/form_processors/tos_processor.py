"""
Module for processing Terms of Service checkboxes in LinkedIn Easy Apply forms.
"""
from loguru import logger
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC

from src.job import Job
from src.easy_apply.form_processors.base_processor import BaseProcessor

class TermsOfServiceProcessor(BaseProcessor):
    """
    Processor for Terms of Service checkboxes in LinkedIn Easy Apply forms.
    """
    
    def handle(self, element: WebElement, job: Job) -> bool:
        """
        Handles 'Terms of Service' checkbox in the form.
        
        Args:
            element (WebElement): The form element containing the terms of service checkbox.
            job (Job): The job object (not used in this method but included for consistent interface).
            
        Returns:
            bool: True if terms of service checkbox was found and clicked, False otherwise.
        """
        labels = element.find_elements(By.TAG_NAME, self.selectors["common"]["label"])
        if not labels:
            return False
            
        # Check if this is a terms of service checkbox
        is_tos = any(
            term in labels[0].text.lower()
            for term in ["terms of service", "privacy policy", "terms of use", "terms & conditions", "agree"]
        )
        
        if is_tos:
            try:
                logger.debug("Found terms of service checkbox")
                
                # First try to find and click the checkbox input directly
                try:
                    # Look for checkbox inputs within the element
                    checkbox_inputs = element.find_elements(By.XPATH, ".//input[@type='checkbox']")
                    if checkbox_inputs:
                        logger.debug(f"Found {len(checkbox_inputs)} checkbox inputs")
                        self.wait.until(EC.element_to_be_clickable(checkbox_inputs[0])).click()
                        logger.debug("Clicked terms of service checkbox input directly")
                        return True
                except Exception as checkbox_error:
                    logger.warning(f"Failed to click checkbox input directly: {checkbox_error}")
                
                # If direct checkbox click fails, try clicking the label as fallback
                self.wait.until(EC.element_to_be_clickable(labels[0])).click()
                logger.debug("Clicked terms of service checkbox label")
                return True
            except Exception as e:
                logger.warning("Failed to click terms of service checkbox", exc_info=True)
        
        return False
