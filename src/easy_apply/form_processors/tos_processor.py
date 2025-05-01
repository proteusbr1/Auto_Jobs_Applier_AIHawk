# src/easy_apply/form_processors/tos_processor.py
"""
Module specifically for processing "Terms of Service", "Privacy Policy",
and similar agreement checkboxes often found in LinkedIn Easy Apply forms.
"""
from __future__ import annotations 
import time
from typing import Final, List, Optional, Any, TYPE_CHECKING

from loguru import logger
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, ElementNotInteractableException,
    StaleElementReferenceException
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC

# Assuming BaseProcessor correctly imports dependencies
from .base_processor import BaseProcessor
# Assuming Job object definition is available (though not used here)
if TYPE_CHECKING:
    from src.job import Job 
else:
    Job: Any = object          



class TermsOfServiceProcessor(BaseProcessor):
    """
    Identifies and checks checkboxes related to agreements like Terms of Service.

    These checkboxes are often mandatory for proceeding with the application.
    """

    # Keywords identifying agreement-related checkboxes (case-insensitive)
    AGREEMENT_KEYWORDS: Final[List[str]] = [
        "terms of service", "privacy policy", "terms of use",
        "terms & conditions", "i agree", "i accept", "i acknowledge",
        "consent", "confirm"
    ]

    def handle(self, element: WebElement, job: Job) -> bool:
        """
        Checks if the element contains an agreement checkbox and clicks it if found.

        Args:
            element (WebElement): The WebElement representing the form section
                                  or element potentially containing the checkbox.
            job (Job): The job object (not directly used but kept for interface consistency).

        Returns:
            bool: True if an agreement checkbox was identified and an attempt was made
                  to click it (success not guaranteed), False if no relevant
                  checkbox was found.
        """
        logger.trace("TermsOfServiceProcessor: Scanning element for agreement checkbox...")

        # Check if the element's text indicates it's an agreement section
        try:
            # Check label first
            label_text = ""
            labels: List[WebElement] = []
            try:
                labels = element.find_elements(By.TAG_NAME, self.selectors["common"]["label"])
                if labels and labels[0].is_displayed():
                    label_text = labels[0].text.lower()
            except StaleElementReferenceException:
                 logger.warning("Stale element getting initial labels in ToS.")
                 # Try re-finding element? For now, proceed cautiously.
                 element_text = "" # Assume we can't get text if stale
            except Exception as e:
                 logger.warning(f"Error getting initial labels in ToS: {e}")
                 element_text = ""

            # Fallback to element text if no clear label or label fetch failed
            if not label_text:
                try:
                    element_text = element.text.lower()
                except StaleElementReferenceException:
                    logger.warning("Stale element getting element text in ToS.")
                    element_text = "" # Cannot proceed if stale here
                except Exception as e:
                    logger.warning(f"Error getting element text in ToS: {e}")
                    element_text = ""
            else:
                 element_text = label_text # Prioritize label text if found


            is_agreement_section = any(keyword in element_text for keyword in self.AGREEMENT_KEYWORDS) if element_text else False

            if not is_agreement_section:
                logger.trace("Element does not appear to be an agreement section based on text.")
                return False

            logger.info(f"Identified potential agreement section: '{element_text[:100]}...'")

            # Find the checkbox input within this section
            checkbox_input: Optional[WebElement] = None
            try:
                 # Use multiple strategies to find the checkbox
                 checkbox_selectors = [
                      self.selectors["checkbox"]["standard"],
                      self.selectors["checkbox"]["data_test"]
                 ]
                 for selector in checkbox_selectors:
                     try:
                         inputs = element.find_elements(By.XPATH, selector)
                         # Find the first visible, enabled checkbox
                         for inp in inputs:
                             if inp.is_displayed() and inp.is_enabled():
                                 checkbox_input = inp
                                 logger.debug(f"Found agreement checkbox input using selector: {selector}")
                                 break
                         if checkbox_input: break # Found it
                     except Exception:
                         continue # Try next selector

                 if not checkbox_input:
                     logger.warning("Could not find an active checkbox input within the agreement section.")
                     # As a last resort, maybe try clicking the label directly?
                     # Re-check labels in case they became available
                     if not labels: # If labels weren't found/were stale initially
                         try:
                             labels = element.find_elements(By.TAG_NAME, self.selectors["common"]["label"])
                         except Exception: labels = [] # Ignore errors finding labels again

                     if labels and labels[0].is_displayed() and labels[0].is_enabled():
                          logger.warning("Attempting to click the agreement label as fallback...")
                          try:
                              self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true); arguments[0].click();", labels[0])
                              logger.info("Clicked agreement label via JS as fallback.")
                              return True # Assume success if JS click doesn't error
                          except Exception as label_click_err:
                               logger.error(f"Failed to click agreement label as fallback: {label_click_err}")
                               return False # Truly failed
                     else:
                         return False # Cannot find checkbox or clickable label

            except StaleElementReferenceException:
                logger.warning("Stale element reference while searching for agreement checkbox.")
                return False
            except Exception as find_err:
                logger.error(f"Error finding agreement checkbox input: {find_err}", exc_info=True)
                return False

            # Click the checkbox if found and not already checked
            if checkbox_input:
                 try:
                     if checkbox_input.is_selected():
                         logger.debug("Agreement checkbox is already checked.")
                         return True # Already handled
                 except StaleElementReferenceException:
                      logger.warning("Stale element checking if agreement checkbox is selected. Assuming not selected.")
                      # Continue to clicking attempt

                 logger.info("Attempting to check the agreement checkbox...")
                 try:
                      # Use JS click for robustness against overlays/custom styling
                      self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true); arguments[0].click();", checkbox_input)
                      time.sleep(0.2) # Allow state to update
                      # Verify selection
                      if checkbox_input.is_selected():
                           logger.info("Successfully checked agreement checkbox.")
                           return True
                      else:
                           logger.error("Failed to check agreement checkbox even after JS click.")
                           # Optional: Try standard click as another fallback?
                           # try:
                           #    self.wait.until(EC.element_to_be_clickable(checkbox_input)).click()
                           #    if checkbox_input.is_selected(): return True
                           # except: pass
                           return False # Failed to check
                 except StaleElementReferenceException:
                      logger.error("Stale element reference while clicking agreement checkbox.")
                      return False
                 except Exception as click_err:
                     logger.error(f"Error clicking agreement checkbox: {click_err}", exc_info=True)
                     return False

        except StaleElementReferenceException:
            logger.warning("Stale element reference encountered while checking element text.")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in TermsOfServiceProcessor: {e}", exc_info=True)
            return False

        return False # Should not be reached normally