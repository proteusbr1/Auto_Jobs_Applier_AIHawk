# src/main.py
"""
Main entry point for the generic web automation bot.

This script orchestrates the configuration validation, browser initialization,
LLM setup, component instantiation, and execution of the automation workflow defined
by the Facade pattern.
"""

import os
import sys
from pathlib import Path
import yaml
import click
import socket
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
import logging

# Third-party libraries
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException
from loguru import logger
from dotenv import load_dotenv

# Internal modules (assuming refactored names and locations)
from src.utils import chrome_browser_options, configure_logging
from src.llm import setup_llm_processor, LLMProcessor, LLMError, ConfigurationError as LLMConfigError
# Assume these components have been renamed and refactored
from src.web_authenticator import WebAuthenticator # Renamed from WebAuthenticator
from src.automation_facade import AutomationFacade # Renamed from AutomationFacade
from src.job_manager import JobManager # Renamed from JobManager
from src.job_application_profile import JobApplicationProfile # Assuming this name is generic enough
from src.resume_manager import ResumeManager

# Configuration (assuming this defines TRYING_DEBUG, etc., or handled differently)
# Consider moving configuration loading logic to a dedicated module
try:
    # Example: importing a central config object or specific values
    from app_config import TRYING_DEBUG
except ImportError:
    logger.warning("app_config.py not found or TRYING_DEBUG not defined. Setting TRYING_DEBUG=False.")
    TRYING_DEBUG = False


# --- Custom Exceptions ---

class ConfigError(Exception):
    """Custom exception for general application configuration errors."""
    pass


# --- Configuration Validation ---

class ConfigValidator:
    """Validates configuration files (YAML) and structure."""

    # Constants for validation keys might be useful
    _REQUIRED_CONFIG_KEYS: Dict[str, type] = {
        'remote': bool,
        'experienceLevel': dict,
        'jobTypes': dict,
        'date': dict,
        'searches': list,
        'distance': int,
        'company_blacklist': list,
        'title_blacklist': list,
        'description_blacklist': list,
        'llm_model_type': str,
        'llm_model': str
        # 'llm_api_url': str # Optional, handled by llm_manager
    }
    _OPTIONAL_CONFIG_KEYS_WITH_DEFAULTS: Dict[str, Any] = {
        'company_blacklist': [],
        'title_blacklist': [],
        'description_blacklist': []
        # 'llm_api_url': None # Example if handling here
    }
    _EXPERIENCE_LEVELS: List[str] = ['internship', 'entry', 'associate', 'mid-senior level', 'director', 'executive']
    _JOB_TYPES: List[str] = ['full-time', 'contract', 'part-time', 'temporary', 'internship', 'other', 'volunteer']
    _DATE_FILTERS: List[str] = ['all time', 'month', 'week', '24 hours']
    _APPROVED_DISTANCES: set = {0, 5, 10, 25, 50, 100}

    @staticmethod
    def _validate_boolean_dict(data: Any, allowed_keys: List[str], dict_name: str, file_path: Path) -> None:
        """Validates a dictionary where keys map to boolean values."""
        if not isinstance(data, dict):
             raise ConfigError(f"'{dict_name}' must be a dictionary in config file {file_path}")
        for key in allowed_keys:
            value = data.get(key)
            if not isinstance(value, bool):
                logger.error(f"Value for '{key}' in '{dict_name}' must be a boolean (true/false) in config file {file_path}. Found: {type(value)}")
                raise ConfigError(f"Value for '{key}' in '{dict_name}' must be a boolean in config file {file_path}")
            logger.trace(f"'{dict_name}' key '{key}' validated.")

    @staticmethod
    def _validate_searches_list(searches: Any, file_path: Path) -> None:
        """Validates the structure of the 'searches' list."""
        if not isinstance(searches, list):
            raise ConfigError(f"'searches' must be a list in config file {file_path}")

        if not searches:
             logger.warning("The 'searches' list in the config file is empty. The bot will not perform any searches.")
             # Decide if this should be an error or just a warning. Warning seems appropriate.
             # raise ConfigError(f"'searches' list cannot be empty in config file {file_path}")

        for index, search in enumerate(searches, start=1):
            if not isinstance(search, dict):
                raise ConfigError(f"Each item in 'searches' must be a dictionary. Issue found at item {index} in {file_path}.")
            if 'location' not in search or not isinstance(search.get('location'), str) or not search.get('location').strip():
                raise ConfigError(f"Each search item requires a non-empty string 'location'. Issue found at item {index} in {file_path}.")
            if 'positions' not in search or not isinstance(search.get('positions'), list):
                raise ConfigError(f"Each search item requires a 'positions' list. Issue found at item {index} in {file_path}.")
            if not search.get('positions'): # Ensure positions list is not empty
                 raise ConfigError(f"'positions' list cannot be empty in search item {index} in {file_path}.")
            if not all(isinstance(pos, str) and pos.strip() for pos in search['positions']):
                raise ConfigError(f"All items in 'positions' must be non-empty strings. Issue found at item {index} in {file_path}.")
            logger.trace(f"'searches' item {index} validated.")

    @staticmethod
    def validate_config_file(yaml_path: Path) -> Dict[str, Any]:
        """
        Validates and loads the main YAML configuration file.

        Args:
            yaml_path (Path): Path to the main configuration YAML file.

        Returns:
            Dict[str, Any]: Validated configuration parameters.

        Raises:
            ConfigError: If the file is missing, invalid YAML, or fails structural/type validation.
        """
        logger.debug(f"Validating main configuration file: {yaml_path}")
        if not yaml_path.exists():
            logger.error(f"Configuration file not found: {yaml_path}")
            raise ConfigError(f"Configuration file not found: {yaml_path}")

        try:
            with open(yaml_path, 'r', encoding='utf-8') as stream:
                config_data = yaml.safe_load(stream)
            if not isinstance(config_data, dict):
                 raise ConfigError(f"Configuration file content must be a YAML dictionary (mapping). Found: {type(config_data)}")
            logger.debug(f"YAML data loaded successfully from {yaml_path}.")
        except yaml.YAMLError as exc:
            logger.error(f"Error parsing YAML file {yaml_path}: {exc}")
            raise ConfigError(f"Error parsing configuration file {yaml_path}: {exc}") from exc
        except IOError as exc:
             logger.error(f"Error reading configuration file {yaml_path}: {exc}")
             raise ConfigError(f"Error reading configuration file {yaml_path}: {exc}") from exc


        # Validate required keys and types
        for key, expected_type in ConfigValidator._REQUIRED_CONFIG_KEYS.items():
            if key not in config_data:
                 # Handle optional keys with defaults
                 if key in ConfigValidator._OPTIONAL_CONFIG_KEYS_WITH_DEFAULTS:
                     config_data[key] = ConfigValidator._OPTIONAL_CONFIG_KEYS_WITH_DEFAULTS[key]
                     logger.warning(f"Optional key '{key}' missing in config. Using default: {config_data[key]}")
                 else:
                     logger.error(f"Missing required key '{key}' in config file {yaml_path}")
                     raise ConfigError(f"Missing required key '{key}' in config file {yaml_path}")
            elif not isinstance(config_data[key], expected_type):
                 # Allow None for lists that default to empty list
                 if expected_type is list and config_data[key] is None and key in ConfigValidator._OPTIONAL_CONFIG_KEYS_WITH_DEFAULTS:
                      config_data[key] = []
                      logger.warning(f"Key '{key}' is None in config. Setting to empty list.")
                 else:
                      logger.error(f"Invalid type for key '{key}' in config file {yaml_path}. Expected {expected_type.__name__}, found {type(config_data[key]).__name__}.")
                      raise ConfigError(f"Invalid type for key '{key}'. Expected {expected_type.__name__}, found {type(config_data[key]).__name__}.")
            logger.trace(f"Config key '{key}' validated.")

        # Specific structure validations
        try:
             ConfigValidator._validate_boolean_dict(config_data.get('experienceLevel'), ConfigValidator._EXPERIENCE_LEVELS, 'experienceLevel', yaml_path)
             ConfigValidator._validate_boolean_dict(config_data.get('jobTypes'), ConfigValidator._JOB_TYPES, 'jobTypes', yaml_path)
             ConfigValidator._validate_boolean_dict(config_data.get('date'), ConfigValidator._DATE_FILTERS, 'date', yaml_path)
             ConfigValidator._validate_searches_list(config_data.get('searches'), yaml_path)
        except ConfigError: # Re-raise validation errors
             raise
        except Exception as e: # Catch unexpected errors during validation
             logger.error(f"Unexpected error during detailed config validation: {e}", exc_info=True)
             raise ConfigError(f"Unexpected validation error in {yaml_path}: {e}") from e


        # Validate distance value
        if config_data.get('distance') not in ConfigValidator._APPROVED_DISTANCES:
            logger.error(f"Invalid 'distance' value {config_data.get('distance')} in config file {yaml_path}. Must be one of: {ConfigValidator._APPROVED_DISTANCES}")
            raise ConfigError(f"Invalid 'distance' value in config file {yaml_path}. Must be one of: {ConfigValidator._APPROVED_DISTANCES}")
        logger.trace("'distance' value validated.")

        # Validate blacklists (type checked above, ensure they are lists now)
        for key in ['company_blacklist', 'title_blacklist', 'description_blacklist']:
             if not isinstance(config_data.get(key), list):
                  # This case should be caught by initial type check or None handling
                  raise ConfigError(f"'{key}' should be a list but is {type(config_data.get(key))} in {yaml_path}")
             # Ensure all elements are strings
             if not all(isinstance(item, str) for item in config_data[key]):
                  raise ConfigError(f"All items in '{key}' must be strings in {yaml_path}")
             logger.trace(f"Blacklist '{key}' validated.")


        logger.info(f"Configuration file '{yaml_path}' validated successfully.")
        return config_data


# --- File Management ---

class FileManager:
    """Handles file operations such as searching, validating paths, and loading content."""

    # Consider making these filenames configurable
    CONFIG_FILENAME = "config.yaml"
    OUTPUT_DIR_NAME = "output"
    DEFAULT_HTML_RESUME_PATH = Path("resumes/resume.html") # Default path for HTML resume
    PRIVATE_CONTEXT_FILENAME = "data_folder/private_context.yaml"



    @staticmethod
    def validate_data_folder_structure(app_data_folder: Path) -> Tuple[Path, Path]:
        """
        Validates the existence of the data folder and required configuration files.
        Creates the output directory if it doesn't exist.

        Args:
            app_data_folder (Path): Path to the application's data folder.

        Returns:
            Tuple[Path, Path]: Paths to config file and output folder.

        Raises:
            ConfigError: If the data folder or required files are missing.
        """
        logger.debug(f"Validating data folder structure at: {app_data_folder}")
        if not app_data_folder.exists() or not app_data_folder.is_dir():
            logger.error(f"Application data folder not found: {app_data_folder}")
            raise ConfigError(f"Application data folder not found: {app_data_folder}")

        config_file = app_data_folder / FileManager.CONFIG_FILENAME

        missing_files = []
        if not config_file.exists():
            missing_files.append(FileManager.CONFIG_FILENAME)

        if missing_files:
            logger.error(f"Missing required files in data folder '{app_data_folder}': {', '.join(missing_files)}")
            raise ConfigError(f"Missing required files in data folder '{app_data_folder}': {', '.join(missing_files)}")

        output_folder = app_data_folder / FileManager.OUTPUT_DIR_NAME
        try:
             output_folder.mkdir(parents=True, exist_ok=True)
             logger.debug(f"Validated/created output folder: {output_folder}")
        except OSError as e:
             logger.error(f"Could not create output directory {output_folder}: {e}")
             raise ConfigError(f"Could not create output directory {output_folder}: {e}") from e


        logger.debug("Data folder structure validated successfully.")
        return config_file, output_folder



# --- Browser Initialization ---

def init_browser() -> webdriver.Chrome:
    """
    Initializes the Selenium Chrome WebDriver with appropriate options.

    Uses WebDriverManager to automatically download/manage the ChromeDriver.

    Returns:
        webdriver.Chrome: An instance of the Chrome WebDriver.

    Raises:
        RuntimeError: If the WebDriver fails to initialize.
    """
    logger.debug("Initializing Chrome WebDriver...")
    try:
        # Use options from the utility module
        options = chrome_browser_options()

        # Setup ChromeDriver service
        service_args = ["--log-level=WARNING"] if TRYING_DEBUG else ["--log-level=OFF"]
        # Specify log path only in debug mode to avoid clutter
        log_path = os.path.join("logs", "chromedriver.log") if TRYING_DEBUG else os.devnull

        # Ensure logs directory exists if logging is enabled
        if TRYING_DEBUG:
             os.makedirs("logs", exist_ok=True)

        service = ChromeService(
            executable_path=ChromeDriverManager().install(),
            service_args=service_args,
            log_path=log_path
        )

        browser = webdriver.Chrome(service=service, options=options)
        logger.info("Chrome WebDriver initialized successfully.")
        # Add implicit wait? browser.implicitly_wait(5) # Example: wait up to 5s for elements
        return browser
    except WebDriverException as e:
        logger.critical(f"WebDriver failed to initialize: {e}", exc_info=True)
        # Provide more helpful error message if possible
        if "net::ERR_CONNECTION_REFUSED" in str(e):
             logger.error("Connection refused - ensure ChromeDriver or browser isn't blocked by firewall/network.")
        elif "session not created" in str(e).lower():
             logger.error("Session not created - check ChromeDriver/Chrome browser version compatibility.")
        raise RuntimeError(f"Failed to initialize Chrome browser: {str(e)}") from e
    except Exception as e:
         # Catch other potential errors like ChromeDriverManager issues
         logger.critical(f"Unexpected error during browser initialization: {e}", exc_info=True)
         raise RuntimeError(f"Unexpected error initializing browser: {e}") from e


# --- Automation Core Logic ---

def setup_and_run_automation(
    parameters: Dict[str, Any],
    llm_processor: LLMProcessor,
    resume_manager: ResumeManager,
    data_folder_path: Path
):
    """
    Sets up the automation components (authenticator, job manager, facade)
    and runs the main automation workflow (login, apply).

    Args:
        parameters (Dict[str, Any]): Validated configuration parameters, including 'outputFileDirectory'.
        llm_processor (LLMProcessor): Initialized LLM processor instance.
        resume_manager (ResumeManager): Initialized resume manager instance.

    Raises:
        WebDriverException: If a browser automation error occurs.
        ConfigError: If essential configuration for components is missing.
        RuntimeError: For other unexpected errors during setup or execution.
    """
    logger.info("Setting up and running automation workflow...")
    browser = None # Ensure browser is defined for finally block
    try:
        # --- Get Resume Info ---
        resume_html_path = resume_manager.get_resume() # Get path to final HTML resume
        logger.info(f"Using HTML resume file: {resume_html_path}")

        # --- Read YAML for JobApplicationProfile ---
        # JobApplicationProfile still needs YAML data, so read it directly
        yaml_path = data_folder_path / "plain_text_resume.yaml"
        if not yaml_path.exists():
            logger.error(f"Required YAML file for profile not found: {yaml_path}")
            raise ConfigError(f"Required YAML file for profile not found: {yaml_path}")
            
        with open(yaml_path, "r", encoding='utf-8') as file:
            yaml_content = file.read()
        
        logger.info(f"Using YAML file for profile data: {yaml_path}")

        # --- Initialize Profile & Browser ---
        job_application_profile = JobApplicationProfile(yaml_content) # Use YAML content for profile
        logger.debug("Job application profile created.")

        browser = init_browser() # Initialize browser for this run

        # --- Initialize Bot Components ---
        # These names should match your refactored component classes
        authenticator = WebAuthenticator(browser)
        job_manager = JobManager(browser) # Pass browser and maybe LLM? Depends on JobManager needs
        # If JobManager needs LLMProcessor:
        # job_manager = JobManager(browser, llm_processor)
        logger.debug("Core automation components initialized (Authenticator, JobManager).")

        # --- Setup Facade ---
        # The Facade coordinates the components
        facade = AutomationFacade(authenticator, job_manager)
        facade.set_llm_processor(llm_processor)
        facade.set_job_application_profile(job_application_profile)
        # Pass necessary parameters (like search criteria, blacklists) and resume manager to facade/components
        facade.configure(parameters, resume_manager) # Add a configure method to Facade?
        logger.debug("Automation Facade configured.")


        # --- Execute Workflow ---
        logger.info("Starting login sequence...")
        facade.login() # Facade method name might differ
        logger.info("Login sequence completed.")

        logger.info("Starting main automation tasks...") # Updated log message
        facade.run_tasks() # <--- CORRECTED METHOD NAME
        logger.info("Main automation tasks finished.") # Updated log message

    except (WebDriverException, ConfigError, LLMError, RuntimeError) as e:
        # Catch known specific errors from setup/execution
        logger.critical(f"Automation failed due to error: {e}", exc_info=True)
        raise # Re-raise the caught exception
    except Exception as e:
        # Catch any truly unexpected errors
        logger.critical(f"An unexpected error occurred during automation: {e}", exc_info=True)
        raise RuntimeError(f"Unexpected automation error: {e}") from e
    finally:
        # --- Cleanup ---
        if browser:
            try:
                logger.info("Closing browser.")
                browser.quit()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}", exc_info=True)
        logger.info("Automation workflow finished.")


# --- Utilities ---

def check_internet(host: str = "8.8.8.8", port: int = 53, timeout: int = 3) -> bool:
    """
    Checks internet connectivity by attempting a socket connection.

    Args:
        host (str): Target host (default: Google DNS).
        port (int): Target port (default: 53/DNS).
        timeout (int): Connection timeout in seconds.

    Returns:
        bool: True if connection succeeds, False otherwise.
    """
    logger.debug(f"Checking internet connection to {host}:{port}...")
    try:
        socket.setdefaulttimeout(timeout)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((host, port))
        logger.debug("Internet connection check successful.")
        return True
    except socket.error as ex:
        logger.warning(f"Internet connection check failed: {ex}")
        return False


# --- Main Application Entry Point ---

@click.command()
@click.option(
    '--resume-pdf', # Changed option name for clarity
    'resume_pdf_path', # Attribute name for the variable
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),
    help="Optional path to the source resume PDF file (if different from default HTML generation)."
)
@click.option(
    '--data-dir',
    'data_folder_path',
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True, path_type=Path),
    default="data_folder", # Default data folder name
    show_default=True,
    help="Path to the application's data directory containing config and resume files."
)
@click.option(
    '--env-file',
    'env_file_path',
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),
    default=".env",
    show_default=True,
    help="Path to the environment file containing API keys."
)
def main(resume_pdf_path: Optional[Path], data_folder_path: Path, env_file_path: Path):
    """
    Generic Web Automation Bot

    This application automates web tasks based on configurations defined in the
    data directory and secrets from the environment file. It typically involves
    logging into websites and performing actions like job searching/applying,
    leveraging Selenium for browser automation and optionally an LLM for processing.
    """
    # --- Basic Setup ---
    start_time = datetime.now()

    # --- Load Environment Variables FIRST ---
    # load_dotenv needs to happen before configure_logging reads env vars
    print(f"Attempting to load environment variables from: {env_file_path.resolve()}") # Basic print for early feedback
    loaded_env = load_dotenv(dotenv_path=env_file_path, override=True)
    if not loaded_env:
         # Use print here as logger might not be fully configured yet
         print(f"Warning: Environment file '{env_file_path}' not found or empty.", file=sys.stderr)

    # --- Configure Logging SECOND ---
    configure_logging()
    logging.getLogger("fontTools").setLevel(logging.ERROR)
    logging.getLogger("fontTools.subset").setLevel(logging.ERROR)
    logging.getLogger("weasyprint").setLevel(logging.ERROR)

    # --- Now use logger safely ---
    logger.info(f"Application started.") # Log after configuration
    logger.info(f"Using data directory: {data_folder_path.resolve()}")
    logger.info(f"Using environment file: {env_file_path.resolve()}")
    if not loaded_env:
        logger.warning(f"Environment file '{env_file_path}' was not found or empty. Defaults will be used.")
    if resume_pdf_path:
         logger.info(f"Optional source resume PDF provided: {resume_pdf_path.resolve()}")


    # --- Initial Checks ---
    if not check_internet():
        logger.critical("No internet connection detected. Exiting.")
        sys.exit(1) # Exit with error code


    try:
        # --- Validate Data Folder and Config ---
        logger.debug("Validating data folder structure...")
        config_file, output_folder = FileManager.validate_data_folder_structure(data_folder_path)

        logger.debug("Validating main configuration file...")
        app_parameters = ConfigValidator.validate_config_file(config_file)
        # Add output dir to params - needed by components?
        app_parameters['outputFileDirectory'] = output_folder

        # --- Initialize Resume Manager ---
        resume_manager = ResumeManager(
            #  resume_option=resume_pdf_path, # PDF path from CLI option
             default_html_resume=FileManager.DEFAULT_HTML_RESUME_PATH,
             private_context_path=FileManager.PRIVATE_CONTEXT_FILENAME
        )
        
        # Ensure the final HTML resume exists or is generated
        final_html_resume_path = resume_manager.get_resume()
        if not final_html_resume_path or not final_html_resume_path.exists():
             raise ConfigError(f"Failed to obtain or generate the final HTML resume from path: {final_html_resume_path}")
        logger.info(f"Resume Manager initialized. Final HTML resume: {final_html_resume_path}")

        # --- Setup LLM Processor ---
        logger.info("Setting up LLM Processor...")
        # The LLM processor will use data from the HTML resume via the resume manager
        llm_processor = setup_llm_processor(
            app_config=app_parameters,
            resume_manager=resume_manager,
        )

        # --- Run Automation ---
        logger.info("Starting main automation process...")
        setup_and_run_automation(app_parameters, llm_processor, resume_manager, data_folder_path)

        logger.success("Automation process completed successfully.") # Use success level

    except (ConfigError, LLMConfigError) as ce:
        logger.critical(f"Configuration Error: {ce}", exc_info=True)
        logger.error("Please check your configuration files (config.yaml, .env) and data folder structure.")
        sys.exit(1) # Exit with error code
    except FileNotFoundError as fnf:
        # Should be caught by ConfigError now, but keep as fallback
        logger.critical(f"File Not Found Error: {fnf}", exc_info=True)
        logger.error("Ensure all required configuration and resume files exist in the data folder.")
        sys.exit(1)
    except LLMError as llme:
        logger.critical(f"LLM Error: {llme}", exc_info=True)
        logger.error("An error occurred during LLM interaction. Check LLM configuration and API keys.")
        sys.exit(1)
    except RuntimeError as rte:
        logger.critical(f"Runtime Error: {rte}", exc_info=True)
        sys.exit(1)
    except Exception as e:
        # Catch-all for truly unexpected errors
        logger.critical(f"An unexpected critical error occurred: {e}", exc_info=True)
        sys.exit(1) # Exit with error code
    finally:
        end_time = datetime.now()
        duration = end_time - start_time
        logger.info(f"Application finished. Total runtime: {duration}")
        # Ensure logs are flushed
        logger.complete()

if __name__ == "__main__":
    main()
