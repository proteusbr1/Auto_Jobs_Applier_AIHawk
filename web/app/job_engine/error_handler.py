"""
Error handling module for the Auto_Jobs_Applier_AIHawk web application.
This module provides error handling and recovery mechanisms for the job application process.
"""
import time
import traceback
from enum import Enum, auto
from typing import Dict, Any, Optional, List, Callable, Tuple

from selenium.common.exceptions import (
    WebDriverException,
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
    JavascriptException
)
from loguru import logger

from app import db
from app.models import JobApplication


class ErrorSeverity(Enum):
    """Enum for error severity levels."""
    LOW = auto()      # Minor error, can continue
    MEDIUM = auto()   # Significant error, may need retry
    HIGH = auto()     # Critical error, should abort
    FATAL = auto()    # Fatal error, should abort and report


class ErrorCategory(Enum):
    """Enum for error categories."""
    AUTHENTICATION = auto()    # Authentication errors
    NAVIGATION = auto()        # Navigation errors
    ELEMENT = auto()           # Element interaction errors
    NETWORK = auto()           # Network errors
    BROWSER = auto()           # Browser errors
    APPLICATION = auto()       # Application errors
    DATABASE = auto()          # Database errors
    SYSTEM = auto()            # System errors
    UNKNOWN = auto()           # Unknown errors


class JobError:
    """Class representing a job application error."""
    
    def __init__(
        self,
        exception: Exception,
        severity: ErrorSeverity,
        category: ErrorCategory,
        message: str,
        context: Dict[str, Any] = None,
        screenshot_path: Optional[str] = None
    ):
        """
        Initialize a job error.
        
        Args:
            exception (Exception): The exception that caused the error.
            severity (ErrorSeverity): The severity of the error.
            category (ErrorCategory): The category of the error.
            message (str): A human-readable error message.
            context (Dict[str, Any], optional): Additional context for the error.
            screenshot_path (str, optional): Path to a screenshot of the error.
        """
        self.exception = exception
        self.severity = severity
        self.category = category
        self.message = message
        self.context = context or {}
        self.screenshot_path = screenshot_path
        self.timestamp = time.time()
        self.traceback = traceback.format_exc()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the error to a dictionary.
        
        Returns:
            Dict[str, Any]: The error as a dictionary.
        """
        return {
            'exception_type': type(self.exception).__name__,
            'severity': self.severity.name,
            'category': self.category.name,
            'message': self.message,
            'context': self.context,
            'screenshot_path': self.screenshot_path,
            'timestamp': self.timestamp,
            'traceback': self.traceback
        }
    
    def __str__(self) -> str:
        """
        Get a string representation of the error.
        
        Returns:
            str: A string representation of the error.
        """
        return f"{self.category.name} error ({self.severity.name}): {self.message}"


class ErrorClassifier:
    """Class for classifying errors."""
    
    @staticmethod
    def classify_exception(
        exception: Exception,
        context: Dict[str, Any] = None
    ) -> Tuple[ErrorSeverity, ErrorCategory, str]:
        """
        Classify an exception.
        
        Args:
            exception (Exception): The exception to classify.
            context (Dict[str, Any], optional): Additional context for classification.
            
        Returns:
            Tuple[ErrorSeverity, ErrorCategory, str]: The severity, category, and message.
        """
        context = context or {}
        
        # Selenium exceptions
        if isinstance(exception, TimeoutException):
            return (
                ErrorSeverity.MEDIUM,
                ErrorCategory.NAVIGATION,
                "Operation timed out. The page may be slow to load or the element may not exist."
            )
        
        if isinstance(exception, NoSuchElementException):
            return (
                ErrorSeverity.MEDIUM,
                ErrorCategory.ELEMENT,
                "Element not found. The page structure may have changed."
            )
        
        if isinstance(exception, StaleElementReferenceException):
            return (
                ErrorSeverity.LOW,
                ErrorCategory.ELEMENT,
                "Element is stale. The page may have been updated."
            )
        
        if isinstance(exception, ElementClickInterceptedException):
            return (
                ErrorSeverity.MEDIUM,
                ErrorCategory.ELEMENT,
                "Element click was intercepted. Another element may be blocking it."
            )
        
        if isinstance(exception, ElementNotInteractableException):
            return (
                ErrorSeverity.MEDIUM,
                ErrorCategory.ELEMENT,
                "Element is not interactable. It may be disabled or hidden."
            )
        
        if isinstance(exception, JavascriptException):
            return (
                ErrorSeverity.MEDIUM,
                ErrorCategory.BROWSER,
                "JavaScript error occurred. The page script may have errors."
            )
        
        if isinstance(exception, WebDriverException):
            if "chrome not reachable" in str(exception).lower():
                return (
                    ErrorSeverity.HIGH,
                    ErrorCategory.BROWSER,
                    "Browser is not reachable. It may have crashed or been closed."
                )
            return (
                ErrorSeverity.HIGH,
                ErrorCategory.BROWSER,
                "WebDriver error occurred. The browser may be in an invalid state."
            )
        
        # Database exceptions
        if isinstance(exception, db.SQLAlchemyError):
            return (
                ErrorSeverity.HIGH,
                ErrorCategory.DATABASE,
                "Database error occurred. The operation could not be completed."
            )
        
        # Default classification
        return (
            ErrorSeverity.HIGH,
            ErrorCategory.UNKNOWN,
            f"Unknown error occurred: {str(exception)}"
        )


class ErrorHandler:
    """Class for handling errors in the job application process."""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        """
        Initialize the error handler.
        
        Args:
            max_retries (int, optional): Maximum number of retries. Defaults to 3.
            base_delay (float, optional): Base delay for exponential backoff. Defaults to 1.0.
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.errors: List[JobError] = []
    
    def handle_exception(
        self,
        exception: Exception,
        context: Dict[str, Any] = None,
        screenshot_func: Optional[Callable[[], Optional[str]]] = None
    ) -> JobError:
        """
        Handle an exception.
        
        Args:
            exception (Exception): The exception to handle.
            context (Dict[str, Any], optional): Additional context for the error.
            screenshot_func (Callable[[], Optional[str]], optional): Function to take a screenshot.
            
        Returns:
            JobError: The job error.
        """
        context = context or {}
        
        # Classify the exception
        severity, category, message = ErrorClassifier.classify_exception(exception, context)
        
        # Take a screenshot if possible
        screenshot_path = None
        if screenshot_func:
            try:
                screenshot_path = screenshot_func()
            except Exception as e:
                logger.warning(f"Failed to take screenshot: {e}")
        
        # Create a job error
        error = JobError(
            exception=exception,
            severity=severity,
            category=category,
            message=message,
            context=context,
            screenshot_path=screenshot_path
        )
        
        # Log the error
        logger.error(f"Job error: {error}")
        if error.severity in [ErrorSeverity.HIGH, ErrorSeverity.FATAL]:
            logger.error(f"Traceback: {error.traceback}")
        
        # Add the error to the list
        self.errors.append(error)
        
        return error
    
    def should_retry(self, error: JobError, retry_count: int) -> bool:
        """
        Determine if an operation should be retried.
        
        Args:
            error (JobError): The error that occurred.
            retry_count (int): The current retry count.
            
        Returns:
            bool: True if the operation should be retried, False otherwise.
        """
        # Don't retry if we've reached the maximum number of retries
        if retry_count >= self.max_retries:
            return False
        
        # Don't retry fatal errors
        if error.severity == ErrorSeverity.FATAL:
            return False
        
        # Always retry low and medium severity errors
        if error.severity in [ErrorSeverity.LOW, ErrorSeverity.MEDIUM]:
            return True
        
        # For high severity errors, only retry certain categories
        if error.severity == ErrorSeverity.HIGH:
            retryable_categories = [
                ErrorCategory.NETWORK,
                ErrorCategory.BROWSER,
                ErrorCategory.NAVIGATION
            ]
            return error.category in retryable_categories
        
        return False
    
    def get_retry_delay(self, retry_count: int) -> float:
        """
        Get the delay before the next retry.
        
        Args:
            retry_count (int): The current retry count.
            
        Returns:
            float: The delay in seconds.
        """
        # Exponential backoff with jitter
        delay = self.base_delay * (2 ** retry_count)
        jitter = delay * 0.1 * (2 * (time.time() % 1) - 1)  # +/- 10% jitter
        return delay + jitter
    
    def update_application_status(self, application: JobApplication, error: JobError):
        """
        Update the status of a job application based on an error.
        
        Args:
            application (JobApplication): The job application to update.
            error (JobError): The error that occurred.
        """
        # Update the application status based on the error severity
        if error.severity == ErrorSeverity.FATAL:
            application.add_status_update('failed', f"Fatal error: {error.message}")
        elif error.severity == ErrorSeverity.HIGH:
            application.add_status_update('error', f"Error: {error.message}")
        
        # Add error details to the application
        app_details = application.application_details
        errors = app_details.get('errors', [])
        errors.append(error.to_dict())
        app_details['errors'] = errors
        application.application_details = app_details
        
        # Save the changes
        db.session.commit()
    
    def get_error_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the errors that occurred.
        
        Returns:
            Dict[str, Any]: A summary of the errors.
        """
        if not self.errors:
            return {'error_count': 0}
        
        # Count errors by severity and category
        severity_counts = {}
        category_counts = {}
        
        for error in self.errors:
            severity_name = error.severity.name
            category_name = error.category.name
            
            severity_counts[severity_name] = severity_counts.get(severity_name, 0) + 1
            category_counts[category_name] = category_counts.get(category_name, 0) + 1
        
        # Get the most recent error
        most_recent = self.errors[-1].to_dict()
        
        return {
            'error_count': len(self.errors),
            'severity_counts': severity_counts,
            'category_counts': category_counts,
            'most_recent': most_recent
        }
