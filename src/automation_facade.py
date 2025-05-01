# src/automation_facade.py
"""
Provides a simplified interface (Facade) for orchestrating the components
involved in the web automation process (e.g., login, task execution).
Manages the state and setup flow of the automation.
"""

from loguru import logger
from typing import List, Optional, Any, Dict

# Import component types for type hinting (assuming these are the refactored names)
from .web_authenticator import WebAuthenticator
from .job_manager import JobManager
from .job_application_profile import JobApplicationProfile
from .llm import LLMProcessor
from .resume_manager import ResumeManager
# Import custom exceptions if needed (e.g., for state validation)
# from .exceptions import ConfigurationError


class AutomationState:
    """
    Manages the internal state of the AutomationFacade to ensure components
    and configurations are properly initialized before operations proceed.
    """

    def __init__(self):
        """Initializes the state tracking flags."""
        logger.debug("Initializing AutomationState.")
        self.reset()

    def reset(self):
        """Resets all state flags to their default (False) values."""
        logger.debug("Resetting AutomationState.")
        self.job_application_profile_set: bool = False
        self.llm_processor_set: bool = False
        self.parameters_set: bool = False # Covers general config and parameters needed
        self.logged_in: bool = False

    def validate_state(self, required_keys: List[str]):
        """
        Validates that all specified state flags are set to True.

        Args:
            required_keys (List[str]): List of state attribute names (flags)
                                       that must be True.

        Raises:
            ValueError: If any required state flag is False.
        """
        logger.debug(f"Validating AutomationState requires: {required_keys}")
        missing = []
        for key in required_keys:
            if not getattr(self, key, False):
                missing.append(self._format_key_name(key))

        if missing:
            error_msg = f"State validation failed. Missing required setup: {', '.join(missing)}. Please ensure all necessary components and configurations are set before proceeding."
            logger.error(error_msg)
            # Consider raising a more specific error like ConfigurationError or StateError
            raise ValueError(error_msg)

        logger.debug("AutomationState validation passed.")

    @staticmethod
    def _format_key_name(key: str) -> str:
        """Formats state key names for user-friendly error messages."""
        # Example: 'llm_processor_set' -> 'Llm processor set'
        return key.replace('_', ' ').capitalize()


class AutomationFacade:
    """
    Facade class orchestrating web automation components.

    Simplifies the interaction with authentication, task execution (e.g., job application),
    LLM processing, and configuration management for the main application flow.
    """

    def __init__(self, authenticator: WebAuthenticator, task_manager: JobManager):
        """
        Initializes the AutomationFacade with necessary components.

        Args:
            authenticator (WebAuthenticator): Component responsible for website authentication.
            task_manager (JobManager): Component responsible for the primary automation tasks
                                        (e.g., finding and applying for jobs).
        """
        logger.debug("Initializing AutomationFacade.")
        if not isinstance(authenticator, WebAuthenticator):
            raise TypeError("authenticator must be an instance of WebAuthenticator")
        if not isinstance(task_manager, JobManager):
             raise TypeError("task_manager must be an instance of JobManager") # Or more generic TaskManager if needed

        self.authenticator = authenticator
        self.task_manager = task_manager # Renamed from apply_component for clarity
        self.state = AutomationState()

        # Placeholders for components/data set later
        self.llm_processor: Optional[LLMProcessor] = None
        self.job_application_profile: Optional[JobApplicationProfile] = None
        self.parameters: Optional[Dict[str, Any]] = None
        self.resume_manager: Optional[ResumeManager] = None

        logger.debug("AutomationFacade initialized.")


    def set_job_application_profile(self, job_application_profile: JobApplicationProfile):
        """
        Sets the user's job application profile data.

        Args:
            job_application_profile (JobApplicationProfile): Object containing parsed profile data.

        Raises:
            TypeError: If job_application_profile is not the expected type.
            ValueError: If job_application_profile is considered empty/invalid.
        """
        logger.debug("Setting job application profile...")
        if not isinstance(job_application_profile, JobApplicationProfile):
             raise TypeError("job_application_profile must be an instance of JobApplicationProfile")
        # Add validation if JobApplicationProfile has an is_valid() or similar method
        self._validate_non_empty(job_application_profile, "Job Application Profile object")

        self.job_application_profile = job_application_profile
        # Pass profile to components that need it *now*? Or wait until configure/run?
        # Let's assume components get configured later or access via facade if needed.
        self.state.job_application_profile_set = True
        logger.debug("Job application profile set successfully.")

    def set_llm_processor(self, llm_processor: LLMProcessor):
        """
        Sets the initialized LLM Processor component.

        Args:
            llm_processor (LLMProcessor): An initialized LLMProcessor instance.

        Raises:
            TypeError: If llm_processor is not an instance of LLMProcessor.
        """
        logger.debug("Setting LLM Processor...")
        if not isinstance(llm_processor, LLMProcessor):
             raise TypeError("llm_processor must be an instance of LLMProcessor")

        self.llm_processor = llm_processor
        # Provide the LLM processor to components that require it (typically the task manager)
        # Assuming task_manager (JobManager) has a method like set_llm_processor
        if hasattr(self.task_manager, 'set_llm_processor'):
             self.task_manager.set_llm_processor(llm_processor)
             logger.debug("LLM Processor passed to Task Manager.")
        else:
             logger.warning(f"Task Manager ({type(self.task_manager).__name__}) does not have a 'set_llm_processor' method. LLM might not be available for tasks.")

        self.state.llm_processor_set = True
        logger.debug("LLM Processor set successfully.")


    def configure(self, parameters: Dict[str, Any], resume_manager: ResumeManager):
        """
        Sets the configuration parameters and resume manager for the automation tasks.

        Args:
            parameters (Dict[str, Any]): Configuration parameters (e.g., search criteria, blacklists).
            resume_manager (ResumeManager): Manager responsible for handling resume files.

        Raises:
            TypeError: If parameters is not a dict or resume_manager is not correct type.
            ValueError: If the parameters dictionary is empty.
        """
        logger.debug("Configuring automation parameters and resume manager...")
        if not isinstance(parameters, dict):
            raise TypeError("parameters must be a dictionary")
        if not isinstance(resume_manager, ResumeManager):
             raise TypeError("resume_manager must be an instance of ResumeManager")

        self._validate_non_empty(parameters, "Configuration parameters")

        self.parameters = parameters
        self.resume_manager = resume_manager

        # Pass parameters and resume manager to components that need them
        # Assuming task_manager (JobManager) has a configure method or similar
        if hasattr(self.task_manager, 'configure'):
            self.task_manager.configure(parameters, resume_manager)
            logger.debug("Parameters and Resume Manager passed to Task Manager.")
        else:
            logger.warning(f"Task Manager ({type(self.task_manager).__name__}) does not have a 'configure' method. Parameters/Resume may not be set.")

        # Update state
        self.state.parameters_set = True
        logger.debug("Automation configuration set successfully.")


    def login(self):
        """
        Initiates the login process using the authenticator component.

        Raises:
            ValueError: If required parameters (potentially needed by authenticator) are not set.
        """
        logger.info("Starting login process via Facade...")
        # Validate state needed *before* login (e.g., maybe parameters contain username/password?)
        # If authenticator needs config, ensure parameters_set is checked
        # self.state.validate_state(['parameters_set']) # Example if creds are in params

        # Assuming authenticator takes necessary details from config or env vars internally
        self.authenticator.start() # Or authenticator.login() - adjust method name as needed
        self.state.logged_in = True
        logger.info("Login process completed successfully.")


    def run_tasks(self): # Renamed from start_apply for generality
        """
        Initiates the main automation tasks using the task manager component.

        Raises:
            ValueError: If required components or state (login, profile, LLM, parameters) are not properly set.
        """
        logger.info("Starting main automation tasks via Facade...")
        # Define the required state flags before running tasks
        required_states = [
            'logged_in',
            'job_application_profile_set',
            'llm_processor_set',
            'parameters_set'
        ]
        self.state.validate_state(required_states)

        # Call the primary method of the task manager
        self.task_manager.start_processing() # Or start_applying(), run_tasks() etc.
        logger.info("Main automation tasks started/completed successfully.")


    # --- Helper Methods ---

    def _validate_non_empty(self, value: Any, name: str):
        """
        Validates that a given value is not None or considered empty.

        Args:
            value (Any): The value to validate.
            name (str): The name of the value for logging/error messages.

        Raises:
            ValueError: If the value is None or empty.
        """
        logger.trace(f"Validating {name} is not empty...")
        is_empty = False
        if value is None:
            is_empty = True
        elif isinstance(value, (str, list, dict, set, tuple)) and not value:
             is_empty = True
        # Add checks for custom objects if they have an is_empty() method

        if is_empty:
            logger.error(f"Validation failed: {name} cannot be empty.")
            raise ValueError(f"{name} cannot be empty.")
        logger.trace(f"{name} validated as not empty.")

    # Removed _ensure_job_profile_and_resume_set as resume is no longer directly managed here