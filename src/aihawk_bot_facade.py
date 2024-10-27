# aihawk_bot_facade.py
from loguru import logger
from typing import List, Optional, Any


class AIHawkBotState:
    """
    Manages the internal state of the AIHawkBotFacade to ensure that all necessary components
    are properly initialized before proceeding with operations.
    """

    def __init__(self):
        logger.debug("Initializing AIHawkBotState")
        self.reset()

    def reset(self):
        """
        Resets all state flags to their default values.
        """
        logger.debug("Resetting AIHawkBotState")
        self.credentials_set: bool = False
        self.api_key_set: bool = False
        self.job_application_profile_set: bool = False
        self.gpt_answerer_set: bool = False
        self.parameters_set: bool = False
        self.logged_in: bool = False

    def validate_state(self, required_keys: List[str]):
        """
        Validates that all required state flags are set to True.

        Args:
            required_keys (List[str]): List of state flags that need to be validated.

        Raises:
            ValueError: If any of the required state flags are not set.
        """
        logger.debug(f"Validating AIHawkBotState with required keys: {required_keys}")
        for key in required_keys:
            if not getattr(self, key, False):
                logger.error(f"State validation failed: {key} is not set")
                raise ValueError(f"{self._format_key_name(key)} must be set before proceeding.")
        logger.debug("State validation passed")

    @staticmethod
    def _format_key_name(key: str) -> str:
        """
        Formats the state key name by replacing underscores with spaces and capitalizing words.

        Args:
            key (str): The state key to format.

        Returns:
            str: The formatted key name.
        """
        return key.replace('_', ' ').capitalize()


class AIHawkBotFacade:
    """
    Facade class that orchestrates the interaction between different components required
    for automating job applications. It manages the setup and execution flow of the bot.
    """

    def __init__(self, login_component: Any, apply_component: Any):
        """
        Initializes the AIHawkBotFacade with the necessary components.

        Args:
            login_component (Any): Component responsible for handling authentication.
            apply_component (Any): Component responsible for managing job applications.
        """
        logger.debug("Initializing AIHawkBotFacade")
        self.login_component = login_component
        self.apply_component = apply_component
        self.state = AIHawkBotState()
        self.job_application_profile: Optional[Any] = None
        self.resume: Optional[Any] = None
        self.parameters: Optional[dict] = None

    def set_job_application_profile_and_resume(self, job_application_profile: Any, resume: Any):
        """
        Sets the job application profile and resume for the bot.

        Args:
            job_application_profile (Any): The user's job application profile.
            resume (Any): The user's resume.

        Raises:
            ValueError: If either the job application profile or resume is empty.
        """
        logger.debug("Setting job application profile and resume")
        self._validate_non_empty(job_application_profile, "Job application profile")
        self._validate_non_empty(resume, "Resume")
        self.job_application_profile = job_application_profile
        self.resume = resume
        self.state.job_application_profile_set = True
        logger.debug("Job application profile and resume set successfully")

    def set_gpt_answerer_and_resume_generator(self, gpt_answerer_component: Any, resume_generator_manager: Any):
        """
        Sets up the GPT answerer and resume generator components.

        Args:
            gpt_answerer_component (Any): Component responsible for generating answers using GPT.
            resume_generator_manager (Any): Component responsible for generating resumes.

        Raises:
            ValueError: If the job application profile and resume are not set before this method is called.
        """
        logger.debug("Setting GPT answerer and resume generator")
        self._ensure_job_profile_and_resume_set()
        gpt_answerer_component.set_job_application_profile(self.job_application_profile)
        gpt_answerer_component.set_resume(self.resume)
        self.apply_component.set_gpt_answerer(gpt_answerer_component)
        self.apply_component.set_resume_generator_manager(resume_generator_manager)
        self.state.gpt_answerer_set = True
        logger.debug("GPT answerer and resume generator set successfully")

    def set_parameters(self, parameters: dict, resume_manager: Any):
        """
        Sets the configuration parameters and resume manager for the apply component.

        Args:
            parameters (dict): Configuration parameters for the bot.
            resume_manager (Any): Manager responsible for handling resume files.

        Raises:
            ValueError: If the parameters dictionary is empty.
        """
        logger.debug("Setting parameters")
        self._validate_non_empty(parameters, "Parameters")
        self.parameters = parameters
        self.apply_component.set_parameters(parameters, resume_manager)
        self.state.credentials_set = True
        self.state.parameters_set = True
        logger.debug("Parameters set successfully")

    def start_login(self):
        """
        Initiates the login process using the login component.

        Raises:
            ValueError: If the credentials have not been set before attempting to log in.
        """
        logger.debug("Starting login process")
        self.state.validate_state(['credentials_set'])
        self.login_component.start()
        self.state.logged_in = True
        logger.debug("Login process completed successfully")

    def start_apply(self):
        """
        Initiates the job application process using the apply component.

        Raises:
            ValueError: If required components (login, job profile, GPT answerer, parameters) are not properly set.
        """
        logger.debug("Starting apply process")
        required_states = [
            'logged_in',
            'job_application_profile_set',
            'gpt_answerer_set',
            'parameters_set'
        ]
        self.state.validate_state(required_states)
        self.apply_component.start_applying()
        logger.debug("Apply process started successfully")

    def _validate_non_empty(self, value: Any, name: str):
        """
        Validates that a given value is not empty.

        Args:
            value (Any): The value to validate.
            name (str): The name of the value for logging purposes.

        Raises:
            ValueError: If the value is empty.
        """
        logger.debug(f"Validating that {name} is not empty")
        if not value:
            logger.error(f"Validation failed: {name} is empty")
            raise ValueError(f"{name} cannot be empty.")
        logger.debug(f"Validation passed for {name}")

    def _ensure_job_profile_and_resume_set(self):
        """
        Ensures that both the job application profile and resume have been set before proceeding.

        Raises:
            ValueError: If either the job application profile or resume has not been set.
        """
        logger.debug("Ensuring job profile and resume are set")
        if not self.state.job_application_profile_set:
            logger.error("Job application profile and resume are not set")
            raise ValueError("Job application profile and resume must be set before proceeding.")
        logger.debug("Job profile and resume are set")
