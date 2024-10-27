# resume_manager.py
from pathlib import Path
from loguru import logger
from typing import Optional


class ResumeNotFoundError(FileNotFoundError):
    """Custom exception raised when the resume file is not found."""
    pass


class ResumeManager:
    """
    Handles loading and validation of the resume.

    Attributes:
        resume_path (Optional[Path]): Path to the user-provided resume file.
        default_html_resume (Path): Path to the default HTML resume file.
        resume_content (Optional[Path]): Path to the loaded resume file.
    """

    def __init__(self, resume_option: Optional[Path], default_html_resume: Path):
        """
        Initializes the ResumeManager with optional user-provided resume and a default resume.

        Args:
            resume_option (Optional[Path]): Path to the user-provided resume file. If None, the default resume is used.
            default_html_resume (Path): Path to the default HTML resume file.

        Raises:
            ResumeNotFoundError: If neither the user-provided resume nor the default resume exists.
        """
        self.resume_path = resume_option
        self.default_html_resume = default_html_resume
        self.resume_content: Optional[Path] = None
        self.load_resume()

    def load_resume(self):
        """
        Loads the resume based on the provided option or defaults to the HTML resume.

        Raises:
            ResumeNotFoundError: If the specified resume file does not exist.
        """
        if self.resume_path:
            logger.info(f"Attempting to load user-provided resume from: {self.resume_path}")
            if self.resume_path.exists() and self.resume_path.is_file():
                self.resume_content = self.resume_path
                logger.info(f"Successfully loaded resume from: {self.resume_content}")
            else:
                logger.error(f"User-provided resume file not found at: {self.resume_path}")
                raise ResumeNotFoundError(f"Resume file not found: {self.resume_path}")
        else:
            logger.debug(f"No user-provided resume found. Using default HTML resume at: {self.default_html_resume}")
            if self.default_html_resume.exists() and self.default_html_resume.is_file():
                self.resume_content = self.default_html_resume
                logger.info(f"Successfully loaded default resume from: {self.resume_content}")
            else:
                logger.error(f"Default HTML resume file not found at: {self.default_html_resume}")
                raise ResumeNotFoundError(f"Default resume file not found: {self.default_html_resume}")

    def get_resume(self) -> Path:
        """
        Returns the path to the loaded resume.

        Returns:
            Path: Path to the loaded resume file.

        Raises:
            ResumeNotFoundError: If the resume has not been loaded.
        """
        if self.resume_content:
            logger.debug(f"Retrieving resume path: {self.resume_content}")
            return self.resume_content
        else:
            logger.error("Attempted to retrieve resume before loading it.")
            raise ResumeNotFoundError("Resume has not been loaded.")
