# src/easy_apply/form_handler.py
"""
Handles interactions within web forms, specifically focusing on navigation
(clicking next/submit) and error checking within job application modals (like LinkedIn Easy Apply).
"""
import time
from typing import List, Optional
from loguru import logger

# Selenium Imports
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementNotInteractableException,
    ElementClickInterceptedException,
    StaleElementReferenceException
)
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Internal Imports
import src.utils as utils
# from src.job import Job # Job object not directly used here anymore


class FormHandler:
    """
    Provides methods for interacting with web forms during automated processes,
    including clicking navigation buttons, handling modals, and checking for errors.
    Tailored for LinkedIn Easy Apply workflow.
    """
    # --- Locators ---
    # Modals
    MODAL_SELECTOR = ".artdeco-modal" # General modal container
    SAFETY_REMINDER_MODAL_XPATH = '//div[contains(@class, "artdeco-modal") and .//h2[contains(text(),"Job search safety reminder")]]'
    SAFETY_CONTINUE_BUTTON_XPATH = '//button[contains(., "Continue applying")]'
    DISMISS_MODAL_BUTTON_SELECTOR = "button.artdeco-modal__dismiss"
    CONFIRM_DISMISS_BUTTON_SELECTOR = "button.artdeco-modal__confirm-dialog-btn" # Often index 0 for Discard

    # Buttons within forms
    PRIMARY_BUTTON_SELECTOR = "button.artdeco-button--primary" # General primary button (Next, Review, Submit)
    SUBMIT_BUTTON_TEXTS = ["submit application", "submit"] # Lowercase texts to check for submit
    NEXT_BUTTON_TEXTS = ["next", "continue"] # Lowercase texts for next/continue
    REVIEW_BUTTON_TEXTS = ["review", "review application"] # Lowercase texts for review

    # Unfollow checkbox
    UNFOLLOW_CHECKBOX_XPATH = "//label[contains(.,'to stay up to date with their page.')]/preceding-sibling::input[@type='checkbox']" # Find checkbox associated with label

    # Error indicators
    ERROR_MESSAGE_SELECTOR_INLINE = ".artdeco-inline-feedback--error" # Old structure?
    ERROR_MESSAGE_SELECTOR_ID = "//*[contains(@id, '-error')]" # IDs often end with -error
    ERROR_CLASS_SELECTOR = "//*[contains(@class, 'error') or contains(@class, 'invalid')]" # General error classes
    ERROR_STYLE_SELECTOR = "//*[contains(@style, 'color: red') or contains(@style, 'color:#ff')]" # Red text check

    # Checkboxes (for error handling)
    UNCHECKED_CHECKBOX_XPATH = "//input[@type='checkbox' and not(@checked)]"
    # --- End Locators ---

    def __init__(self, driver: WebDriver, wait_time: int = 10):
        """
        Initializes the FormHandler.

        Args:
            driver (WebDriver): The Selenium WebDriver instance.
            wait_time (int): Default wait time for explicit waits (seconds).
        """
        if not isinstance(driver, WebDriver): raise TypeError("driver must be WebDriver")
        self.driver = driver
        self.wait = WebDriverWait(self.driver, wait_time)
        logger.debug("FormHandler initialized.")

    def handle_job_search_safety_reminder(self) -> None:
        """Handles the 'Job search safety reminder' modal if it appears."""
        logger.debug("Checking for 'Job search safety reminder' modal...")
        try:
            # Use a shorter wait specifically for this optional modal
            short_wait = WebDriverWait(self.driver, 3)
            modal = short_wait.until(EC.visibility_of_element_located((By.XPATH, self.SAFETY_REMINDER_MODAL_XPATH)))
            logger.info("Job search safety reminder modal detected.")
            continue_button = modal.find_element(By.XPATH, self.SAFETY_CONTINUE_BUTTON_XPATH)
            if self._is_element_clickable(continue_button, wait_time=2):
                continue_button.click()
                logger.info("Clicked 'Continue applying' button in safety modal.")
                # Wait for modal to disappear
                WebDriverWait(self.driver, 5).until(EC.invisibility_of_element(modal))
            else:
                 logger.warning("Safety reminder 'Continue' button found but not clickable.")
        except TimeoutException:
            logger.debug("No 'Job search safety reminder' modal detected or it disappeared quickly.")
        except NoSuchElementException:
            logger.debug("Safety reminder 'Continue' button not found within modal.")
        except Exception as e:
            logger.warning(f"Unexpected error handling safety reminder modal: {e}", exc_info=True)


    def click_easy_apply_buttons_sequentially(self) -> bool:
        """
        Procura um botão ‘Easy Apply’ na página do emprego e clica.
        Retorna True se o modal apareceu (início do formulário), False caso contrário.
        """

        EASY_APPLY_XPATH = (
            # topo da página, barra fixa e cartão lateral de lista
            '//button[contains(@aria-label,"Easy Apply") and '
            '(contains(@class,"jobs-apply-button") or '
            ' contains(@class,"jobs-apply-button--top-card") or '
            ' contains(@data-control-name,"jobdetails_topcard_inapply"))]'
        )

        def _attempt_click() -> bool:
            """
            Procura TODOS os botões “Easy Apply”, escolhe o primeiro realmente
            visível/habilitado e tenta clicar.  Devolve True se o modal aparecer.
            """
            try:
                # 1) lazy-scroll – garante que os botões sejam renderizados
                html_el = self.driver.find_element(By.TAG_NAME, "html")
                utils.scroll_slow(self.driver, html_el)

                # 2) localiza todos os candidatos
                WebDriverWait(self.driver, 6).until(
                    EC.presence_of_element_located((By.XPATH, EASY_APPLY_XPATH))
                )
                buttons: List[WebElement] = self.driver.find_elements(
                    By.XPATH, EASY_APPLY_XPATH
                )

                if not buttons:
                    logger.error("Nenhum botão ‘Easy Apply’ encontrado.")
                    return False

                # 3) escolhe o primeiro visível/habilitado
                target: Optional[WebElement] = None
                for btn in buttons:
                    try:
                        if btn.is_displayed() and btn.is_enabled():
                            target = btn
                            break
                    except StaleElementReferenceException:
                        continue  # elemento sumiu, tenta o próximo

                if not target:
                    logger.error("Todos os botões ‘Easy Apply’ encontrados estão ocultos.")
                    return False

                # 4) leva ao viewport e clica (com JS caso click normal falhe)
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", target
                )
                try:
                    WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(target))
                    target.click()
                except Exception:
                    # fallback JS click
                    self.driver.execute_script("arguments[0].click();", target)

                logger.info("Clicked ‘Easy Apply’ button.")

                # 5) confirma que o modal abriu
                if self._is_modal_displayed(wait_time=5):
                    logger.debug("Easy Apply modal detected.")
                    return True
                logger.warning("Modal did not appear after click.")
                return False

            except TimeoutException:
                logger.error("Não foi possível encontrar/clicar no botão ‘Easy Apply’.")
                return False
            except Exception as e:
                logger.error(f"Erro inesperado clicando ‘Easy Apply’: {e}", exc_info=True)
                return False


        # Primeira tentativa
        if _attempt_click():
            return True

        # Se falhou, tenta uma vez após refresh (com screenshot para depuração)
        utils.capture_screenshot(self.driver, "easy_apply_retry_refresh")
        logger.info("Retrying after page refresh...")
        self.driver.refresh()
        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        if _attempt_click():
            return True

        # Se ainda falhar, faz screenshot final e devolve False
        utils.capture_screenshot(self.driver, "easy_apply_button_timeout")
        return False


    def _is_element_clickable(self, element: WebElement, wait_time: Optional[int] = None) -> bool:
        """Checks if an element is visible and enabled (clickable)."""
        try:
            effective_wait_time = wait_time if wait_time is not None else self.wait._timeout # Use custom or default wait
            custom_wait = WebDriverWait(self.driver, effective_wait_time)
            custom_wait.until(EC.visibility_of(element))
            is_enabled = element.is_enabled()
            logger.trace(f"Element visibility: True, Enabled: {is_enabled}")
            return is_enabled # Clickable primarily means enabled for buttons
        except TimeoutException:
             logger.trace("Element not visible within timeout.")
             return False
        except StaleElementReferenceException:
             logger.warning("Stale element reference checking clickability.")
             return False
        except Exception as e:
            logger.warning(f"Error checking element clickability: {e}")
            return False


    def _is_modal_displayed(self, wait_time: int = 5) -> bool:
        """Checks if the Easy Apply modal is currently visible."""
        try:
            short_wait = WebDriverWait(self.driver, wait_time)
            modal = short_wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, self.MODAL_SELECTOR)))
            logger.trace("Modal is visible.")
            return True
        except TimeoutException:
            logger.trace("Modal not visible within timeout.")
            return False
        except Exception as e:
            logger.warning(f"Error checking modal visibility: {e}")
            return False


    def next_or_submit(self) -> bool:
        """
        Clicks the primary action button ('Submit', 'Next', 'Review') in the form modal.

        Returns:
            bool: True if 'Submit' was clicked (indicating completion), False if 'Next' or 'Review'
                  was clicked (indicating more steps), raises Exception on failure to find/click button.
        """
        logger.debug("Attempting to find and click 'Submit', 'Next', or 'Review' button...")
        try:
             # Wait for *any* primary button to be potentially clickable first
             self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, self.PRIMARY_BUTTON_SELECTOR)))
             # Fetch all primary buttons within the modal (be specific)
             modal_element = self.driver.find_element(By.CSS_SELECTOR, self.MODAL_SELECTOR)
             buttons = modal_element.find_elements(By.CSS_SELECTOR, self.PRIMARY_BUTTON_SELECTOR)

             if not buttons:
                  logger.error("No primary buttons found within the modal.")
                  raise NoSuchElementException("No primary action button found in modal.")

             submit_button: Optional[WebElement] = None
             next_review_button: Optional[WebElement] = None
             active_button: Optional[WebElement] = None # The button to click

             # Identify the correct button
             for button in buttons:
                  if not button.is_displayed(): continue # Skip hidden buttons
                  button_text = button.text.strip().lower()
                  logger.trace(f"Checking button text: '{button_text}'")

                  if any(submit_text in button_text for submit_text in self.SUBMIT_BUTTON_TEXTS):
                       submit_button = button
                       break # Prioritize submit
                  elif not next_review_button and any(nav_text in button_text for nav_text in self.NEXT_BUTTON_TEXTS + self.REVIEW_BUTTON_TEXTS):
                       next_review_button = button
                       # Don't break yet, keep checking for submit

             if submit_button and self._is_element_clickable(submit_button, wait_time=2):
                  active_button = submit_button
                  logger.info("Found 'Submit' button.")
                  self._unfollow_company_if_present() # Try to unfollow before final submit
                  logger.info("Clicking 'Submit Application' button...")
                  active_button.click()
                  # Wait for modal/button to disappear/become stale
                  self.wait.until(EC.staleness_of(active_button))
                  logger.info("Application Submitted Successfully.")
                  return True # Application finished
             elif next_review_button and self._is_element_clickable(next_review_button, wait_time=2):
                  active_button = next_review_button
                  button_text = active_button.text.strip()
                  logger.info(f"Found '{button_text}' button.")
                  logger.info(f"Clicking '{button_text}' button...")
                  active_button.click()
                  time.sleep(1.5) # Allow time for next section/errors to load
                  self._check_for_errors() # Check for errors *after* clicking next/review
                  logger.debug("Proceeding to next step.")
                  return False # More steps remain
             else:
                  # Log available buttons if expected ones aren't found/clickable
                  available_buttons = [(b.text.strip(), b.is_enabled()) for b in buttons if b.is_displayed()]
                  logger.error(f"Could not find a clickable 'Submit', 'Next', or 'Review' button. Available primary buttons: {available_buttons}")
                  raise ElementNotInteractableException("No actionable primary button found.")

        except (NoSuchElementException, ElementNotInteractableException, TimeoutException, StaleElementReferenceException) as e:
             logger.error(f"Error interacting with form navigation buttons: {e}", exc_info=True)
             utils.capture_screenshot(self.driver, "form_navigation_error")
             raise # Re-raise the exception to be handled by the caller (_fill_application_form)
        except Exception as e:
             logger.error(f"Unexpected error during next_or_submit: {e}", exc_info=True)
             utils.capture_screenshot(self.driver, "form_navigation_unexpected_error")
             raise # Re-raise unexpected errors


    def _unfollow_company_if_present(self) -> None:
        """Attempts to uncheck the 'follow company' checkbox if found."""
        try:
            # Use a short wait as this checkbox might not always be present
            unfollow_checkbox = WebDriverWait(self.driver, 2).until(
                EC.element_to_be_clickable((By.XPATH, self.UNFOLLOW_CHECKBOX_XPATH))
            )
            if unfollow_checkbox.is_selected():
                 logger.info("Attempting to unfollow company...")
                 unfollow_checkbox.click()
                 logger.info("Unchecked 'Follow company' checkbox.")
            else:
                 logger.debug("'Follow company' checkbox found but already unchecked.")
        except TimeoutException:
            logger.debug("'Follow company' checkbox not found or not clickable.")
        except Exception as e:
            logger.warning(f"Could not unfollow company (non-critical error): {e}")


    def _check_for_errors(self) -> None:
        """
        Checks for validation error messages within the form after attempting to proceed.
        Raises an exception if errors are found.
        """
        logger.debug("Checking for form validation errors...")
        errors_found = []
        error_elements = []
        try:
            # Combine selectors for efficiency
            error_elements = self.driver.find_elements(By.CSS_SELECTOR, self.ERROR_MESSAGE_SELECTOR_INLINE) \
                           + self.driver.find_elements(By.XPATH, self.ERROR_MESSAGE_SELECTOR_ID) \
                           + self.driver.find_elements(By.XPATH, self.ERROR_CLASS_SELECTOR) \
                           + self.driver.find_elements(By.XPATH, self.ERROR_STYLE_SELECTOR)

            # Filter visible elements with actual error text
            for element in error_elements:
                try:
                    if element.is_displayed() and element.text.strip():
                        errors_found.append(element.text.strip())
                except StaleElementReferenceException:
                     logger.warning("Stale element encountered while checking for errors.")
                     continue # Skip stale element

            if errors_found:
                 unique_errors = sorted(list(set(errors_found))) # Remove duplicates
                 error_summary = "; ".join(unique_errors)
                 logger.error(f"Form validation errors detected: {error_summary}")
                 utils.capture_screenshot(self.driver, "form_validation_errors")

                 # Specific check and attempt to fix checkbox errors
                 if any("check box" in e.lower() or "must select" in e.lower() for e in unique_errors):
                      logger.warning("Potential checkbox error detected. Attempting to check required boxes.")
                      self._handle_checkbox_errors()

                 # Raise an exception to stop the current step
                 raise ValueError(f"Form validation failed: {error_summary}")
            else:
                 logger.debug("No form validation errors detected.")

        except Exception as e:
            # If the error check itself fails, or if errors were found and raised ValueError
            if isinstance(e, ValueError): # Re-raise the validation error
                raise e
            else:
                 logger.error(f"Error occurred while checking for form errors: {e}", exc_info=True)
                 # Don't raise here unless the check failure should stop the process
                 # raise RuntimeError(f"Failure during error checking: {e}") from e


    def _handle_checkbox_errors(self) -> None:
         """Attempts to find and check any unchecked required checkboxes."""
         try:
              # Find checkboxes potentially marked as required or associated with errors
              # This might need specific selectors based on how errors are linked to fields
              required_checkboxes = self.driver.find_elements(By.XPATH, self.UNCHECKED_CHECKBOX_XPATH + "[ancestor::div[contains(@class, 'required') or contains(@class, 'error')]]") # Example refinement
              if not required_checkboxes:
                   # Fallback to finding any unchecked checkbox
                   required_checkboxes = self.driver.find_elements(By.XPATH, self.UNCHECKED_CHECKBOX_XPATH)

              logger.debug(f"Found {len(required_checkboxes)} potential unchecked required checkboxes.")
              for checkbox in required_checkboxes:
                   try:
                        if not checkbox.is_selected():
                             logger.info("Attempting to click an unchecked required checkbox...")
                             # Scroll into view if needed
                             self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", checkbox)
                             time.sleep(0.2)
                             checkbox.click()
                             logger.info("Clicked checkbox.")
                   except Exception as click_err:
                        logger.warning(f"Failed to click required checkbox: {click_err}")
         except Exception as find_err:
              logger.warning(f"Could not find or process required checkboxes: {find_err}")


    def discard_application(self) -> None:
        """Attempts to close the Easy Apply modal and discard the application."""
        logger.warning("Attempting to discard current application...")
        try:
            # Click the main dismiss button (X)
            dismiss_button = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, self.DISMISS_MODAL_BUTTON_SELECTOR)))
            dismiss_button.click()
            logger.debug("Clicked modal dismiss button.")
            time.sleep(0.5) # Allow confirmation dialog to appear

            # Check for and click the confirmation discard button
            try:
                 # Confirmation button might be index 0 or 1 depending on layout
                 confirm_dialog = WebDriverWait(self.driver, 3).until(EC.visibility_of_element_located((By.CLASS_NAME, "artdeco-modal__actionbar")))
                 confirm_buttons = confirm_dialog.find_elements(By.TAG_NAME, "button")
                 discard_button = None
                 for btn in confirm_buttons:
                      if "discard" in btn.text.lower():
                           discard_button = btn
                           break
                 if discard_button and self._is_element_clickable(discard_button, wait_time=2):
                      discard_button.click()
                      logger.info("Confirmed discarding application.")
                      # Wait for modal to fully close
                      WebDriverWait(self.driver, 5).until(EC.invisibility_of_element_located((By.CSS_SELECTOR, self.MODAL_SELECTOR)))
                 else:
                      logger.warning("Could not find or click confirmation discard button.")
            except TimeoutException:
                 logger.debug("Discard confirmation dialog did not appear or timed out.")
            except Exception as confirm_e:
                 logger.warning(f"Error interacting with discard confirmation: {confirm_e}")

        except TimeoutException:
            logger.warning("Could not find dismiss button for application modal.")
        except Exception as e:
            logger.error(f"Failed to discard application: {e}", exc_info=True)