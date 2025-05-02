# src/easy_apply/file_uploader.py
"""
Handles file uploads (Resumes, Cover Letters) within web automation forms,
including dynamic generation of personalized documents using an LLM.
"""
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger
# Selenium Imports
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Internal Imports
import src.utils as utils # Assuming utils has ensure_directory
from src.job import Job
from src.llm import LLMProcessor # Use refactored name
# Utility for file operations
from .file_utils import generate_humanized_filename, check_file_size
# Utility for PDF generation
from .pdf_generator import render_resume_html, generate_pdf_from_html, generate_pdf_from_text
# Utility for loading HTML template
from .resume_template_loader import load_resume_template


class FileUploader:
     """
     Manages uploading files to form input fields. Supports generating personalized
     resumes and cover letters on-the-fly using an LLMProcessor.
     """
     # Locators
     SHOW_MORE_RESUMES_XPATH = "//button[contains(@aria-label, 'Show') and contains(@aria-label, 'more resumes')]"
     FILE_INPUT_XPATH = "//input[@type='file']"

     def __init__(self,
                    driver: WebDriver,
                    llm_processor: LLMProcessor, # Changed parameter name
                    default_resume_path: Optional[Path] = None, # Use Path object
                    wait_time: int = 10):
          """
          Initializes the FileUploader.

          Args:
               driver (WebDriver): The Selenium WebDriver instance.
               llm_processor (LLMProcessor): The initialized LLM processor for generating content.
               default_resume_path (Optional[Path]): Path to a default resume file (PDF or HTML) to use if provided.
               wait_time (int): Default wait time for explicit waits (seconds).
          """
          logger.debug("Initializing FileUploader...")
          if not isinstance(driver, WebDriver): raise TypeError("driver must be WebDriver")
          if not isinstance(llm_processor, LLMProcessor): raise TypeError("llm_processor must be LLMProcessor")
          if default_resume_path and not isinstance(default_resume_path, Path):
               default_resume_path = Path(default_resume_path)

          self.driver = driver
          self.wait = WebDriverWait(self.driver, wait_time)
          self.llm_processor = llm_processor # Store LLM Processor
          self.default_resume_path = default_resume_path
          self.user_resume_html_template: Optional[str] = None # Loaded on demand or init

          # Load HTML template immediately if needed for generation
          try:
               self.user_resume_html_template = load_resume_template()
               if self.user_resume_html_template:
                    logger.debug("HTML resume template loaded successfully.")
               else:
                    # This is critical if generation is needed
                    logger.error("Failed to load HTML resume template. Resume generation will fail.")
                    # Decide: raise error now or let it fail later? Raising now is clearer.
                    raise ValueError("HTML resume template failed to load, cannot initialize FileUploader.")
          except Exception as e:
               logger.error(f"Error loading HTML resume template during init: {e}", exc_info=True)
               raise # Re-raise critical error

          logger.debug("FileUploader initialized.")


     def handle_upload_fields(self, element: WebElement, job: Job) -> None:
          """
          Handles file upload fields within a given parent element (e.g., a form section).
          Determines if the field is for a resume or cover letter and processes accordingly.

          Args:
               element (WebElement): The parent WebElement containing the upload field(s).
               job (Job): The job object for context (title, company, description).
          """
          logger.info("Handling file upload field(s)...")

          # Look for file input elements within the provided parent element
          # This assumes 'element' is the container for the label input
          try:
               file_inputs = element.find_elements(By.XPATH, ".//input[@type='file']")
               if not file_inputs:
                    logger.warning("No file input elements found within the provided element. Cannot handle upload.")
                    return
               logger.debug(f"Found {len(file_inputs)} file input(s) within the element.")
          except Exception as e:
               logger.error(f"Error finding file input elements within provided element: {e}", exc_info=True)
               return


          for file_input in file_inputs:
               try:
                    # Ensure input is visible for interaction
                    self.driver.execute_script(
                         "arguments[0].style.display = 'block'; arguments[0].style.visibility = 'visible';",
                         file_input
                    )
                    logger.trace("Made file input element visible.")

                    # Determine field type (Resume or Cover Letter) using LLM on label text
                    # Find the associated label text - complex task, might need better selectors
                    field_label = self._get_field_label(file_input)
                    if not field_label:
                         logger.warning("Could not determine label for file input. Skipping.")
                         continue

                    upload_type = self.llm_processor.check_resume_or_cover(field_label)
                    logger.debug(f"Determined upload type for label '{field_label}': {upload_type}")

                    if "resume" in upload_type:
                         logger.info("Processing RESUME upload field.")
                         self._handle_resume_upload(file_input, job)
                    elif "cover" in upload_type:
                         logger.info("Processing COVER LETTER upload field.")
                         self._handle_cover_letter_upload(file_input, job)
                    else:
                         logger.warning(f"Upload type '{upload_type}' is unrecognized for label '{field_label}'. Skipping field.")

               except Exception as e:
                    logger.error(f"Failed processing a file input field: {e}", exc_info=True)
                    # Continue to next file input if one fails
                    continue
          time.sleep(5)
          logger.info("Finished handling file upload field(s).")


     def _get_field_label(self, file_input_element: WebElement) -> str:
          """Attempts to find the text label associated with a file input element."""
          # Try finding label by 'for' attribute matching input 'id'
          try:
               input_id = file_input_element.get_attribute('id')
               if input_id:
                    label = self.driver.find_element(By.XPATH, f"//label[@for='{input_id}']")
                    if label.text: return label.text.strip()
          except: pass # Ignore errors, try next method

          # Try finding label within the parent element hierarchy
          try:
               # Go up a few levels, find label/span/div with relevant text
               parent = file_input_element.find_element(By.XPATH, "..") # Immediate parent
               label_like = parent.find_elements(By.XPATH, ".//label | .//span[contains(@class, 'label')] | .//legend")
               if label_like and label_like[0].text: return label_like[0].text.strip()
               # Try grandparent
               parent = parent.find_element(By.XPATH, "..")
               label_like = parent.find_elements(By.XPATH, ".//label | .//span[contains(@class, 'label')] | .//legend")
               if label_like and label_like[0].text: return label_like[0].text.strip()
               # Use immediate parent's text as last resort
               if parent.text: return parent.text.strip()
          except Exception as e:
               logger.warning(f"Could not reliably determine label for file input: {e}")

          return "" # Return empty if label not found


     def _handle_resume_upload(self, file_input_element: WebElement, job: Job) -> None:
          """Handles the logic for uploading a resume."""
          # Option 1: Use default resume path if provided
          if self.default_resume_path and self.default_resume_path.is_file():
               resume_path_to_upload = self.default_resume_path
               logger.info(f"Using provided default resume path: {resume_path_to_upload}")

               # Check if it's HTML - needs generation
               if resume_path_to_upload.suffix.lower() == '.html':
                    logger.debug("Default resume is HTML, generating PDF...")
                    pdf_path = self._generate_pdf_resume_from_html(job) # Generate personalized PDF
                    if not pdf_path:
                         logger.error("Failed to generate PDF from default HTML resume. Cannot upload.")
                         return # Stop if PDF generation fails
                    resume_path_to_upload = pdf_path
               # If it's already PDF or other format, use directly (add checks if needed)
               elif resume_path_to_upload.suffix.lower() != '.pdf':
                    logger.warning(f"Default resume path has unsupported extension: {resume_path_to_upload.suffix}. Attempting upload anyway.")
                    # Add logic here if only PDF is allowed by the website

          # Option 2: Generate resume if no default path provided or default was HTML
          elif self.user_resume_html_template: # Check if template is loaded
               logger.info("No default resume path provided or default was HTML. Generating new personalized resume PDF...")
               pdf_path = self._generate_pdf_resume_from_html(job)
               if not pdf_path:
                    logger.error("Failed to generate personalized PDF resume. Cannot upload.")
                    return # Stop if PDF generation fails
               resume_path_to_upload = pdf_path
          else:
               logger.error("Cannot upload resume: No default path provided and HTML template failed to load.")
               return # Cannot proceed

          # Perform the upload
          try:
               abs_path = str(resume_path_to_upload.resolve())
               logger.debug(f"Attempting to upload resume: {abs_path}")
               file_input_element.send_keys(str(abs_path))
               # Store path in job object if needed
               job.pdf_path = resume_path_to_upload.resolve()
               time.sleep(1) # Brief pause for upload processing
               try:
                    file_name_only = Path(abs_path).name  # “Resume_Foo_Bar.pdf”
                    # 1. aguarda o cartão com esse nome aparecer
                    card_xpath = (".//div[contains(@class,'jobs-document-upload-redesign-card__container')"
                                   f"]//h3[contains(normalize-space(), '{file_name_only}')]"
                                   "/ancestor::div[contains(@class,'jobs-document-upload-redesign-card__container')]")
                    card = self.wait.until(
                         EC.visibility_of_element_located((By.XPATH, card_xpath))
                    )

                    # 2. se ainda não estiver selecionado, clicar no label / container
                    if "Selected" not in card.get_attribute("aria-label"):
                         # clicar no label – mais confiável que no div
                         label = card.find_element(
                              By.XPATH,
                              ".//label[contains(@class,'jobs-document-upload-redesign-card__toggle-label')]")
                         self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", label)
                         label.click()
                         time.sleep(0.3)

                    # 3. confirmar seleção
                    if "Selected" in card.get_attribute("aria-label"):
                         logger.info(f"Resume uploaded **and selected**: {file_name_only}")
                    else:
                         logger.warning(f"Upload ok mas cartão não ficou marcado para '{file_name_only}'.")
               except Exception as sel_err:
                   logger.error(f"Falha ao selecionar cartão do resume: {sel_err}", exc_info=True)
          except Exception as e:
               logger.error(f"Failed to upload resume file '{resume_path_to_upload}': {e}", exc_info=True)
               utils.capture_screenshot(self.driver, "resume_upload_failed")
               # Potentially raise error to stop application process?


     def _generate_pdf_resume_from_html(self, job: Job) -> Optional[Path]:
          """Generates a personalized PDF resume from the HTML template."""
          if not self.user_resume_html_template:
               logger.error("Cannot generate PDF resume: HTML template not loaded.")
               return None
          try:
               logger.debug("Generating personalized resume summary...")
               # Note: USER_RESUME_SUMMARY was removed, adjust prompt if needed or pass summary explicitly
               keywords = self.llm_processor.extract_keywords_from_job_description()
               personalized_summary = self.llm_processor.generate_tailored_summary(keywords)
               logger.debug(f"Personalized summary generated: {personalized_summary[:100]}...")

               rendered_html = render_resume_html(self.user_resume_html_template, personalized_summary)
               logger.debug("Resume HTML rendered.")

               folder_path = Path("generated_cv")
               utils.ensure_directory(folder_path)
               datetime_str = datetime.now().strftime("%Y%m%d_%H%M%S") # Include seconds for uniqueness
               file_name = generate_humanized_filename("Resume", job.title, job.company, datetime_str)
               file_path = folder_path / file_name

               generate_pdf_from_html(rendered_html, file_path)
               check_file_size(file_path, 2 * 1024 * 1024) # 2 MB limit

               logger.info(f"Generated personalized resume PDF: {file_path}")
               return file_path
          except Exception as e:
               logger.error(f"Failed to generate personalized resume PDF: {e}", exc_info=True)
               utils.capture_screenshot(self.driver, "generate_resume_pdf_failed")
               return None


     def _handle_cover_letter_upload(self, file_input_element: WebElement, job: Job) -> None:
          """Handles the logic for generating and uploading a cover letter."""
          try:
               logger.info("Generating personalized cover letter PDF...")
               pdf_path = self._generate_pdf_cover_letter(job)
               if not pdf_path:
                    logger.error("Failed to generate cover letter PDF. Cannot upload.")
                    return # Stop if PDF generation fails

               # Perform the upload
               abs_path = str(pdf_path.resolve())
               logger.debug(f"Attempting to upload cover letter: {abs_path}")
               file_input_element.send_keys(str(abs_path))
               # Store path in job object if needed
               job.cover_letter_path = pdf_path.resolve()
               time.sleep(1) # Brief pause
               logger.info(f"Cover letter uploaded successfully: {abs_path}")

          except Exception as e:
               logger.error(f"Failed to upload cover letter file '{pdf_path if 'pdf_path' in locals() else 'N/A'}': {e}", exc_info=True)
               utils.capture_screenshot(self.driver, "cover_letter_upload_failed")
               # Potentially raise error


     def _generate_pdf_cover_letter(self, job: Job) -> Optional[Path]:
          """Generates a personalized PDF cover letter."""
          try:
               logger.debug("Generating cover letter content using LLM...")
               # Use LLM Processor's resume content as context
               base_resume_content = self.llm_processor._raw_resume # Access internal state - needs getter ideally
               keywords = self.llm_processor.extract_keywords_from_job_description()
               cover_letter_text = self.llm_processor.generate_cover_letter(keywords) # Uses job context set previously

               if not cover_letter_text:
                    logger.error("LLM failed to generate cover letter content.")
                    return None

               logger.debug(f"Generated cover letter text: {cover_letter_text[:150]}...")

               folder_path = Path("generated_cv")
               utils.ensure_directory(folder_path)
               datetime_str = datetime.now().strftime("%Y%m%d_%H%M%S")
               file_name = generate_humanized_filename("CoverLetter", job.title, job.company, datetime_str)
               file_path = folder_path / file_name

               generate_pdf_from_text(file_path, cover_letter_text, f"Cover Letter for {job.title}")
               check_file_size(file_path, 2 * 1024 * 1024) # 2 MB limit

               logger.info(f"Generated personalized cover letter PDF: {file_path}")
               return file_path
          except Exception as e:
               logger.error(f"Failed to generate personalized cover letter PDF: {e}", exc_info=True)
               utils.capture_screenshot(self.driver, "generate_cover_letter_pdf_failed")
               return None
