"""
Module for handling file uploads in LinkedIn Easy Apply forms.
"""
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from loguru import logger
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import src.utils as utils
from src.job import Job
from src.llm.llm_manager import LLMAnswerer
from data_folder.personal_info import USER_RESUME_SUMMARY, USER_RESUME_CHATGPT
from src.easy_apply.file_utils import generate_humanized_filename, check_file_size
from src.easy_apply.pdf_generator import render_resume_html, generate_pdf_from_html, generate_pdf_from_text

class FileUploader:
    """
    Handles file uploads in LinkedIn Easy Apply forms.
    """
    
    def __init__(self, driver: WebDriver, gpt_answerer: LLMAnswerer, resume_path: Optional[str] = None, wait_time: int = 10):
        """
        Initialize the FileUploader with a WebDriver instance.
        
        Args:
            driver (WebDriver): The Selenium WebDriver instance.
            gpt_answerer (LLMAnswerer): The GPT answerer instance for generating personalized content.
            resume_path (Optional[str]): The path to the resume file.
            wait_time (int): The maximum time to wait for elements to appear.
        """
        self.driver = driver
        self.wait = WebDriverWait(self.driver, wait_time)
        self.gpt_answerer = gpt_answerer
        self.resume_path = resume_path
        self.user_resume_html = None
        self._load_resume_html()
    
    def _load_resume_html(self) -> None:
        """
        Loads the resume HTML template.
        """
        from src.easy_apply.resume_template_loader import load_resume_template
        self.user_resume_html = load_resume_template()
        if self.user_resume_html is None:
            logger.error("Failed to load the resume template.")
            raise ValueError("Failed to load the resume template.")
    
    def handle_upload_fields(self, element: WebElement, job: Job) -> None:
        """
        Handles file upload fields in the application form, such as resumes and cover letters.
        Differentiates between PDF and HTML resumes to handle them appropriately.
        
        Args:
            element (WebElement): The WebElement representing the file upload field.
            job (Job): The job object containing job details.
        """
        logger.debug("Handling upload fields")

        # Attempt to click 'Show more resumes' button if it exists
        show_more_button_xpath = "//button[contains(@aria-label, 'Show') and contains(@aria-label, 'more resumes')]"
        try:
            show_more_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, show_more_button_xpath)))
            show_more_button.click()
            logger.debug("Clicked 'Show more resumes' button")
        except TimeoutException:
            logger.debug("'Show more resumes' button not found; proceeding with available upload fields")

        # Find all file upload elements
        file_upload_elements = self.driver.find_elements(By.XPATH, "//input[@type='file']")
        logger.debug(f"Found {len(file_upload_elements)} file upload elements")

        for file_element in file_upload_elements:
            # Make the file input visible if it's hidden
            self.driver.execute_script("arguments[0].classList.remove('hidden')", file_element)
            logger.debug("Made file upload element visible")

            # Determine if the upload field is for a resume or cover letter
            parent_text = file_element.find_element(By.XPATH, "..").text.lower()
            upload_type = self.gpt_answerer.resume_or_cover(parent_text)

            if "resume" in upload_type:
                logger.debug("Detected upload field for resume")
                if self.resume_path and Path(self.resume_path).is_file():
                    resume_extension = Path(self.resume_path).suffix.lower()
                    if resume_extension == '.pdf':
                        logger.debug("Resume is a PDF. Uploading directly.")
                        try:
                            file_element.send_keys(str(Path(self.resume_path).resolve()))
                            logger.info(f"Resume uploaded successfully from path: {self.resume_path}")
                        except Exception as e:
                            logger.error(f"Failed to upload PDF resume from path: {self.resume_path}", exc_info=True)
                            raise
                    elif resume_extension == '.html':
                        logger.debug("Resume is an HTML file. Generating and uploading PDF.")
                        try:
                            self.create_and_upload_resume(file_element, job)
                            logger.info("HTML resume converted to PDF and uploaded successfully.")
                        except Exception as e:
                            logger.error("Failed to create and upload the PDF from HTML resume.", exc_info=True)
                            raise
                    else:
                        logger.warning(f"Unsupported resume format: {resume_extension}. Skipping upload.")
                else:
                    logger.info("Resume path is invalid or not found; generating new resume.")
                    self.create_and_upload_resume(file_element, job)
            elif "cover" in upload_type:
                logger.debug("Detected upload field for cover letter. Uploading cover letter.")
                try:
                    self.create_and_upload_cover_letter(file_element, job)
                    logger.info("Cover letter uploaded successfully.")
                except Exception as e:
                    logger.error("Failed to create and upload the personalized cover letter.", exc_info=True)
                    raise
            else:
                logger.warning(f"Unexpected upload type detected: {upload_type}. Skipping field.")

        logger.debug("Finished handling upload fields")
    
    def create_and_upload_resume(self, element: WebElement, job: Job) -> None:
        """
        Generates a personalized resume and uploads it to the application form.
        
        Args:
            element (WebElement): The WebElement of the upload field for the resume.
            job (Job): The job object containing job details.
        """
        logger.debug("Creating and uploading personalized resume.")
        try:
            # 0. Generate keywords from the job description
            keywords = self.gpt_answerer.extract_keywords_from_job_description(job.description)
            logger.debug(f"Keywords generated: {keywords}")
            
            # 1. Generate the personalized summary
            personalized_summary = self.gpt_answerer.generate_summary_based_on_keywords(
                USER_RESUME_CHATGPT, USER_RESUME_SUMMARY, keywords
            ) 
            logger.debug(f"Personalized summary: {personalized_summary}")

            # 2. Render the HTML with the personalized summary
            rendered_html = render_resume_html(self.user_resume_html, personalized_summary)
            logger.debug("Resume HTML rendered with the personalized summary.")

            # 3. Set the path to save the PDF
            folder_path = "generated_cv"
            utils.ensure_directory(folder_path)

            # 4. Generate a more humanized filename with size limits
            datetime_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
            file_name = generate_humanized_filename(
                prefix="Resume",
                job_title=job.title,
                company_name=job.company,
                datetime_str=datetime_str
            )
            file_path_pdf = os.path.join(folder_path, file_name)

            # 5. Generate the PDF from the rendered HTML
            generate_pdf_from_html(rendered_html, file_path_pdf)

            # 6. Check the file size
            check_file_size(file_path_pdf, 2 * 1024 * 1024)  # 2 MB
            logger.debug(f"File size checked: {file_path_pdf}")

            # 7. Upload the PDF
            element.send_keys(os.path.abspath(file_path_pdf))
            job.pdf_path = os.path.abspath(file_path_pdf)
            time.sleep(2)
            logger.debug("Personalized resume uploaded successfully.")
        except Exception as e:
            logger.error("Failed to create and upload the personalized resume.", exc_info=True)
            utils.capture_screenshot(self.driver, "create_and_upload_resume_exception")
            raise
    
    def create_and_upload_cover_letter(self, element: WebElement, job: Job) -> None:
        """
        Generates a personalized cover letter and uploads it to the application form.
        
        Args:
            element (WebElement): The WebElement of the upload field for the cover letter.
            job (Job): The job object containing job details.
        """
        logger.debug("Creating and uploading personalized cover letter.")
        try:
            # 0. Extract keywords from the job description
            keywords = self.gpt_answerer.extract_keywords_from_job_description(job.description)
            logger.debug(f"Keywords extracted for cover letter: {keywords}")
            
            # 1. Generate the tailored cover letter using keywords
            cover_letter = self.gpt_answerer.generate_cover_letter_based_on_keywords(
                job.description, self.user_resume_html, keywords
            )
            logger.debug(f"Generated cover letter: {cover_letter}")
                       
            # 2. Set the path to save the PDF
            folder_path = "generated_cv"
            utils.ensure_directory(folder_path)

            # 3. Generate a more humanized filename with size limits
            datetime_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
            file_name = generate_humanized_filename(
                prefix="Cover_Letter",
                job_title=job.title,
                company_name=job.company,
                datetime_str=datetime_str
            )
            file_path_pdf = os.path.join(folder_path, file_name)

            # 4. Generate the PDF from the rendered HTML
            generate_pdf_from_text(file_path_pdf, cover_letter, "Cover Letter")
            logger.debug(f"Cover letter PDF generated at: {file_path_pdf}")

            # 5. Check the file size
            check_file_size(file_path_pdf, 2 * 1024 * 1024)  # 2 MB
            logger.debug(f"Cover letter file size is within the allowed limit: {file_path_pdf}")

            # 6. Upload the PDF
            element.send_keys(os.path.abspath(file_path_pdf))
            job.cover_letter_path = os.path.abspath(file_path_pdf)
            time.sleep(2)
            logger.debug("Personalized cover letter uploaded successfully.")
        
        except Exception as e:
            logger.error("Failed to create and upload the personalized cover letter.", exc_info=True)
            utils.capture_screenshot(self.driver, "create_and_upload_cover_letter_exception")
            raise
