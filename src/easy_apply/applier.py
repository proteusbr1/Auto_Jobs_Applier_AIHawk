# src/easy_apply/applier.py
"""
Handles the step-by-step process of filling and submitting LinkedIn Easy Apply forms.
"""
import time
from typing import Optional, Any, List
from pathlib import Path # Import Path
from loguru import logger

# Selenium Imports
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementNotInteractableException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
    WebDriverException
)
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.expected_conditions import (
    visibility_of_element_located,
    presence_of_element_located,
)

# Internal Imports
# Ensure correct relative import if job.py is in parent dir
try:
    from ..job import Job, JobCache, JobStatus # Relative import
except ImportError:
    from src.job import Job, JobCache, JobStatus
try:
    from ..llm import LLMProcessor # Relative import
except ImportError:
    from src.llm import LLMProcessor
try:
    from ..resume_manager import ResumeManager # Relative import
except ImportError:
    from src.resume_manager import ResumeManager
try:
    from .. import utils # Relative import
except ImportError:
    logger.error("Failed to import src.utils using relative path.")
    utils = None

# Easy Apply Components (Relative imports)
from .answer_storage import AnswerStorage
from .job_info_extractor import JobInfoExtractor
from .form_handler import FormHandler
from .form_processors.processor_manager import FormProcessorManager
from .file_uploader import FileUploader

# Configuration (Consider passing these values instead of direct import)
try:
    from app_config import (
        MIN_SCORE_APPLY,
        SALARY_EXPECTATIONS,
        USE_JOB_SCORE,
        USE_SALARY_EXPECTATIONS,
        TRYING_DEBUG,
    )
except ImportError:
    logger.warning("Could not import from app_config. Using default values for apply checks.")
    MIN_SCORE_APPLY = 7.0
    SALARY_EXPECTATIONS = 50000
    USE_JOB_SCORE = True
    USE_SALARY_EXPECTATIONS = True
    TRYING_DEBUG = False


class EasyApplyHandler:
    """
    Automates filling and submitting LinkedIn 'Easy Apply' job application forms.
    """
    DEFAULT_WAIT_TIME = 10
    MAX_FORM_FILL_ATTEMPTS = 10
    MAX_FORM_ERRORS_PER_JOB = 2

    def __init__(
        self,
        driver: WebDriver,
        resume_manager: ResumeManager,
        llm_processor: LLMProcessor,
        cache: Optional[JobCache] = None,
        wait_time: Optional[int] = None,
    ):
        """Initializes the EasyApplyHandler."""
        logger.info("Initializing EasyApplyHandler...")
        if not isinstance(driver, WebDriver): raise TypeError("driver must be WebDriver")
        if not isinstance(resume_manager, ResumeManager): raise TypeError("resume_manager must be ResumeManager")
        if not isinstance(llm_processor, LLMProcessor): raise TypeError("llm_processor must be LLMProcessor")
        if cache and not isinstance(cache, JobCache): raise TypeError("cache must be JobCache or None")

        self.driver = driver
        self.wait_time = wait_time if wait_time is not None else self.DEFAULT_WAIT_TIME
        self.wait = WebDriverWait(self.driver, self.wait_time)
        self.resume_manager = resume_manager
        self.llm_processor = llm_processor
        self.cache = cache

        # Initialize helper components
        # Use output dir from cache if available, else default
        output_dir = cache.output_directory if cache else Path("data_folder/output")
        self.answer_storage = AnswerStorage(output_dir=output_dir)
        self.job_info_extractor = JobInfoExtractor(driver, self.wait_time)
        self.form_handler = FormHandler(driver, self.wait_time)
        self.form_processor_manager = FormProcessorManager(
            driver, self.llm_processor, self.answer_storage, self.wait_time
        )
        self.file_uploader = FileUploader(
            driver, self.llm_processor, self.resume_manager.get_resume(), self.wait_time
        )

        self.is_debug_mode = TRYING_DEBUG
        if self.is_debug_mode: logger.warning("EasyApplyHandler running in DEBUG MODE. Score/Salary checks bypassed.")
        logger.info("EasyApplyHandler initialized successfully.")


    def main_job_apply(self, job: Job) -> bool:
        """Main method to handle the Easy Apply process for a single job."""
        if not isinstance(job, Job) or not job.link: logger.error("Invalid Job object passed."); return False

        logger.info(f"--- Starting for {job.link} ' ---")
        logger.debug(f"Job '{job.title}' at '{job.company}")

        try:
            # Set initial context (description might be None/empty)
            # self.llm_processor.set_current_job(job)
            # logger.debug("Initial job context set in LLM Processor.")

            # 1. Navigate and Extract Info
            logger.debug(f"Navigating to job page: {job.link}")
            self.driver.get(job.link)
            self.job_info_extractor.check_for_premium_redirect(job.link)

            logger.debug("Extracting job details (description, salary)...")
            extracted_description = self.job_info_extractor.get_job_description()
            logger.debug(f"Extracted description type: {type(extracted_description)}, length: {len(extracted_description or '')}")
            if not extracted_description or not isinstance(extracted_description, str):
                 logger.error("JobInfoExtractor failed to return a valid description string!")
                 job.description = None
            else:
                 job.description = extracted_description

            job.salary = self.job_info_extractor.get_job_salary()
            logger.debug(f"Assigned Description Length: {len(job.description or '')}")
            logger.debug(f"Extracted Salary: '{job.salary or 'Not Found'}'")

            # Re-set LLM context AFTER getting description
            logger.debug(f"Attempting to update LLM context. Job Desc is now: {job.description[:100] if job.description else 'None'}...")
            try:
                self.llm_processor.set_current_job(job)
                logger.debug("LLM Processor context updated successfully with extracted details.")
            except ValueError as ve:
                 logger.error(f"LLM Processor validation failed AFTER description extraction: {ve}. Job Desc Length={len(job.description or '')}")
                 if "description" in str(ve).lower() and not job.description: logger.critical("Description is None/empty even after extraction attempt. Cannot proceed.")
                 if self.cache: self.cache.record_job_status(job, JobStatus.FAILED_APPLICATION); self.cache.record_job_status(job, JobStatus.SEEN)
                 return False
            except Exception as e:
                 logger.error(f"Unexpected error updating LLM job context: {e}", exc_info=True)
                 if self.cache: self.cache.record_job_status(job, JobStatus.FAILED_APPLICATION); self.cache.record_job_status(job, JobStatus.SEEN)
                 return False

            # 2. Evaluate Job Suitability (Skip if in debug mode)
            if self.is_debug_mode:
                logger.warning("DEBUG MODE: Bypassing score and salary checks.")
                proceed = True
            else:
                 proceed = self._evaluate_job_suitability(job)

            if not proceed:
                logger.debug("Job does not meet suitability criteria. Skipping application.")
                if self.cache: self.cache.record_job_status(job, JobStatus.SEEN) # Ensure seen if skipped here
                return False

            # 3. Initiate Easy Apply
            logger.debug("Attempting to click 'Easy Apply' button...")
            if not self.form_handler.click_easy_apply_buttons_sequentially():
                 logger.error("Failed to initiate Easy Apply (button click or modal issue).")
                 if self.cache: self.cache.record_job_status(job, JobStatus.FAILED_APPLICATION); self.cache.record_job_status(job, JobStatus.SEEN)
                 return False

            self.form_handler.handle_job_search_safety_reminder()

            # 4. Fill & Submit Form
            logger.info("Starting application form filling process...")
            submitted_successfully = self._fill_and_submit_form(job)

            if submitted_successfully:
                 logger.success(f"Application form submitted successfully for job: {job.link}")
                 return True # Let JobApplier handle success recording
            else:
                 logger.error(f"Application form filling/submission failed for job: {job.link}")
                 if self.cache: self.cache.record_job_status(job, JobStatus.FAILED_APPLICATION); self.cache.record_job_status(job, JobStatus.SEEN)
                 #self.form_handler.discard_application()
                 return False

        except RuntimeError as e: # Catch specific errors like Premium redirect failure
             logger.error(f"Runtime error during application process for {job.link}: {e}", exc_info=True)
             if self.cache: self.cache.record_job_status(job, JobStatus.FAILED_APPLICATION); self.cache.record_job_status(job, JobStatus.SEEN)
             return False
        except Exception as e:
            logger.critical(f"Unexpected critical error during main_job_apply for {job.link}: {e}", exc_info=True)
            if utils: utils.capture_screenshot(self.driver, f"main_apply_critical_error_{job.company}")
            if self.cache: self.cache.record_job_status(job, JobStatus.FAILED_APPLICATION); self.cache.record_job_status(job, JobStatus.SEEN)
            # try: self.form_handler.discard_application()
            # except: pass
            return False
        finally:
             logger.debug(f"--- Finished Easy Apply Process for: '{job.title}' at '{job.company}' ---")


    def _evaluate_job_suitability(self, job: Job) -> bool:
        """Evaluates job score and salary against configured thresholds."""
        # --- CORRECTED SYNTAX ---
        proceed = True # Start assuming we proceed

        # 1. Evaluate Score (if enabled)
        if USE_JOB_SCORE:
             if job.score is None:
                  logger.debug("Calculating job score...")
                  job.score = self.llm_processor.evaluate_job_fit()
                  logger.info(f"Calculated Job Score: {job.score:.2f}")
                  if self.cache:
                      self.cache.record_job_status(job, JobStatus.JOB_SCORE) # Record score status
             else:
                  logger.info(f"Using existing Job Score: {job.score:.2f}")

             if job.score < MIN_SCORE_APPLY:
                  logger.debug(f"Job score {job.score:.2f} is below minimum threshold {MIN_SCORE_APPLY}. Skipping.")
                  if self.cache:
                      self.cache.record_job_status(job, JobStatus.SKIPPED_LOW_SCORE) # Record reason
                  proceed = False # Mark to skip
             else:
                  logger.debug(f"Job score {job.score:.2f} meets threshold {MIN_SCORE_APPLY}.")
        else:
             logger.debug("Job score check is disabled (USE_JOB_SCORE=False).")

        # 2. Evaluate Salary (if enabled AND score passed)
        if proceed and USE_SALARY_EXPECTATIONS:
             logger.debug("Estimating job salary...")
             job.gpt_salary = self.llm_processor.estimate_salary()
             logger.info(f"Estimated Salary: {job.gpt_salary:.0f} USD (Expected: >{SALARY_EXPECTATIONS:.0f} USD)")

             if job.gpt_salary < SALARY_EXPECTATIONS:
                  logger.info(f"Estimated salary {job.gpt_salary:.0f} below expectation {SALARY_EXPECTATIONS:.0f}. Skipping.")
                  if self.cache:
                      self.cache.record_job_status(job, JobStatus.SKIPPED_LOW_SALARY) # Record reason
                  proceed = False # Mark to skip
             else:
                  logger.debug(f"Estimated salary {job.gpt_salary:.0f} meets expectation {SALARY_EXPECTATIONS:.0f}.")
        elif proceed: # Check skipped because USE_SALARY_EXPECTATIONS was false
             logger.debug("Salary expectation check is disabled (USE_SALARY_EXPECTATIONS=False).")

        if proceed:
            logger.debug("Job meets suitability criteria. Proceeding.")

        return proceed


    # ──────────────────────────────────────────────────────────────────────
    # New: locate container for the *current* step (form OR review)
    # ──────────────────────────────────────────────────────────────────────
    def _locate_step_container(self) -> WebElement:
        """
        Return the visible container of the current Easy-Apply step.

        Tries, in order:
        1. `<form>` inside the modal (regular steps)
        2. `.artdeco-modal__content` inside the modal (review step)
        3. The modal root itself (last fallback)

        Raises
        ------
        TimeoutException
            If none of the selectors appear within `self.wait_time`.
        """
        selectors = [
            f"{self.form_handler.MODAL_SELECTOR} form",
            f"{self.form_handler.MODAL_SELECTOR} .artdeco-modal__content",
            self.form_handler.MODAL_SELECTOR,
        ]
        for css in selectors:
            try:
                return self.wait.until(visibility_of_element_located((By.CSS_SELECTOR, css)))
            except TimeoutException:
                continue
        # If we get here, nothing matched
        raise TimeoutException("Could not locate active Easy-Apply step container")


    # ──────────────────────────────────────────────────────────────────────
    # Re-written main loop
    # ──────────────────────────────────────────────────────────────────────
    def _fill_and_submit_form(self, job: Job) -> bool:  # noqa: C901  (complexity ok here)
        logger.debug(f"Starting form filling loop for job: {job.link}")
        form_step = 0
        form_errors = 0

        while form_step < self.MAX_FORM_FILL_ATTEMPTS:
            form_step += 1
            logger.info(f"Processing form step {form_step}/{self.MAX_FORM_FILL_ATTEMPTS}…")

            try:
                container = self._locate_step_container()
                logger.debug("Active modal container located.")

                # ─── Review page? nothing to fill ───────────────────────
                if self._is_review_page(container):
                    logger.info("📝  Review page detected – skipping fill.")
                else:
                    self._fill_up_step(container, job)

                # ─── Next / Submit ─────────────────────────────────────
                if self.form_handler.next_or_submit():
                    logger.info(f"Application submitted successfully on step {form_step}.")
                    return True    # 🎉 done
                else:
                    logger.debug("Moved to next step.")
                    form_errors = 0        # reset counter
                    time.sleep(0.4)
                    continue               # loop for next step

            except TimeoutException as te:
                form_errors += 1
                logger.warning(
                    f"Timeout locating elements on step {form_step} "
                    f"(error {form_errors}/{self.MAX_FORM_ERRORS_PER_JOB}): {te}"
                )
            except Exception as exc:
                form_errors += 1
                logger.error(
                    f"Unexpected error on step {form_step} "
                    f"(error {form_errors}/{self.MAX_FORM_ERRORS_PER_JOB}): {exc!r}",
                    exc_info=True,
                )

            # ─── error handling / abort logic ─────────────────────────
            if utils:
                utils.capture_screenshot(
                    self.driver,
                    f"form_step_{form_step}_error_{type(exc).__name__ if 'exc' in locals() else 'timeout'}",
                )
            if form_errors >= self.MAX_FORM_ERRORS_PER_JOB:
                logger.error("Maximum form errors reached — aborting application.")
                return False

        # Out of steps
        logger.error("Reached MAX_FORM_FILL_ATTEMPTS without submitting.")
        if utils:
            utils.capture_screenshot(self.driver, "form_max_steps_reached")
        return False


    def _fill_up_step(self, form_area: WebElement, job: Job) -> None:
        """Processes all interactive form elements within the current form area/step."""
        logger.debug("Processing elements in current form step...")
    
       # 1. Review page?  ->  nada a preencher
        if self._is_review_page(form_area):
            logger.info("Review page detectada – nenhum campo a preencher.")
            return
        
        section_selectors = [
            ".//div[contains(@class,'jobs-easy-apply-form-section__grouping')]",
            ".//div[contains(@class,'fb-dash-form-element')]",
            ".//fieldset[contains(@class,'form__input--fieldset')]",
            ".//div[contains(@class,'pb4')]",
            ".//div[contains(@class,'jobs-document-upload')]",
            ".//div[contains(@class,'jobs-document-upload-redesign-card__container')]",
        ]
        unique_elements = []
        for selector in section_selectors:
             try: unique_elements.extend(form_area.find_elements(By.XPATH, selector))
             except NoSuchElementException: continue
        unique_elements = list(dict.fromkeys(unique_elements).keys())
        # ─── FALLBACK NOVO ─────────────────────────────────────────────
        if not unique_elements:                       # nada encontrado
            file_inputs = form_area.find_elements(By.XPATH, ".//input[@type='file']")
            if file_inputs:
                self.logger.info(
                    f"Fallback ativo: detectados {len(file_inputs)} <input type='file'> no passo."
                )
                # Envie cada input (ou seu contêiner) para o FileUploader
                for file_input in file_inputs:
                    self.file_uploader.handle_upload_fields(file_input, job)
                return                                # passo tratado
        # ───────────────────────────────────────────────────────────────
        logger.debug(f"Found {len(unique_elements)} potential form sections/elements.")

        if not unique_elements:
             logger.warning("No processable form elements found in current step.")
             try:
                  # Check specifically for review page content
                  if form_area.find_elements(By.CSS_SELECTOR, 'div.jobs-easy-apply-review-content'):
                       logger.info("Detected Review Page content.")
                       return # Nothing to fill on review page
             except: pass # Ignore errors finding review content

        processed_count = 0
        for element in unique_elements:
            try:
                 logger.debug(f"Processing element {processed_count+1}/{len(unique_elements)}...")
                 is_upload = bool(element.find_elements(By.XPATH, ".//input[@type='file']"))
                 if is_upload:
                      logger.debug("Detected file upload section.")
                      self.file_uploader.handle_upload_fields(element, job)
                 else:
                      logger.debug("Passing section to FormProcessorManager.")
                      self.form_processor_manager.process_form_section(element, job)
                 processed_count += 1
            except StaleElementReferenceException:
                 logger.warning("Stale element encountered processing form step. Skipping element.")
                 continue # Skip this specific element
            except Exception as e:
                 logger.error(f"Error processing form element/section: {e}", exc_info=True)
                 continue # Skip this element on error

        logger.debug(f"Finished processing {processed_count} elements in current step.")

    @staticmethod
    def _is_review_page(container: WebElement) -> bool:
        """
        Retorna True quando o container atual contém o cabeçalho
        'Review your application', indicando que estamos na etapa de
        revisão final (100 %) onde não há formulários editáveis.
        """
        try:
            return bool(
                container.find_elements(
                    By.XPATH,
                    ".//h3[contains(normalize-space(),'Review your application')]"
                )
            )
        except Exception:
            # Qualquer erro (stale, no such element, etc.) -> assume que não é review
            return False