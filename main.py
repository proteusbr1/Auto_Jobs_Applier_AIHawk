import os
import re
import sys
from pathlib import Path
import yaml
import click
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException
from lib_resume_builder_AIHawk import Resume, StyleManager, FacadeManager, ResumeGenerator
from src.utils import chrome_browser_options
from src.llm.llm_manager import GPTAnswerer
from src.aihawk_authenticator import AIHawkAuthenticator
from src.aihawk_bot_facade import AIHawkBotFacade
from src.aihawk_job_manager import AIHawkJobManager
from src.job_application_profile import JobApplicationProfile
from loguru import logger
from dotenv import load_dotenv

# Suppress other stderr outputs
sys.stderr = open(os.devnull, 'w')

class ConfigError(Exception):
    pass

class ConfigValidator:
    @staticmethod
    def validate_email(email: str) -> bool:
        logger.debug(f"Validating email: {email}")
        return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email) is not None
    
    @staticmethod
    def validate_yaml_file(yaml_path: Path) -> dict:
        logger.debug(f"Validating YAML file at: {yaml_path}")
        try:
            with open(yaml_path, 'r') as stream:
                data = yaml.safe_load(stream)
                logger.debug(f"YAML data loaded: {data}")
                return data
        except yaml.YAMLError as exc:
            logger.error(f"Error reading YAML file {yaml_path}: {exc}")
            raise ConfigError(f"Error reading file {yaml_path}: {exc}")
        except FileNotFoundError:
            logger.error(f"YAML file not found: {yaml_path}")
            raise ConfigError(f"File not found: {yaml_path}")
    
    @staticmethod
    def validate_config(config_yaml_path: Path) -> dict:
        logger.info(f"Validating configuration file: {config_yaml_path}")
        parameters = ConfigValidator.validate_yaml_file(config_yaml_path)
        required_keys = {
            'remote': bool,
            'experienceLevel': dict,
            'jobTypes': dict,
            'date': dict,
            'positions': list,
            'locations': list,
            'distance': int,
            'company_blacklist': list,
            'title_blacklist': list,
            'llm_model_type': str,
            'llm_model': str
        }

        for key, expected_type in required_keys.items():
            if key not in parameters:
                if key in ['company_blacklist', 'title_blacklist']:
                    parameters[key] = []
                    logger.warning(f"Missing key '{key}' in config. Setting default empty list.")
                else:
                    logger.error(f"Missing or invalid key '{key}' in config file {config_yaml_path}")
                    raise ConfigError(f"Missing or invalid key '{key}' in config file {config_yaml_path}")
            elif not isinstance(parameters[key], expected_type):
                if key in ['company_blacklist', 'title_blacklist'] and parameters[key] is None:
                    parameters[key] = []
                    logger.warning(f"Key '{key}' is None in config. Setting to empty list.")
                else:
                    logger.error(f"Invalid type for key '{key}' in config file {config_yaml_path}. Expected {expected_type}.")
                    raise ConfigError(f"Invalid type for key '{key}' in config file {config_yaml_path}. Expected {expected_type}.")
            else:
                logger.debug(f"Key '{key}' validated successfully.")

        experience_levels = ['internship', 'entry', 'associate', 'mid-senior level', 'director', 'executive']
        for level in experience_levels:
            if not isinstance(parameters['experienceLevel'].get(level), bool):
                logger.error(f"Experience level '{level}' must be a boolean in config file {config_yaml_path}")
                raise ConfigError(f"Experience level '{level}' must be a boolean in config file {config_yaml_path}")
            logger.debug(f"Experience level '{level}' is valid.")

        job_types = ['full-time', 'contract', 'part-time', 'temporary', 'internship', 'other', 'volunteer']
        for job_type in job_types:
            if not isinstance(parameters['jobTypes'].get(job_type), bool):
                logger.error(f"Job type '{job_type}' must be a boolean in config file {config_yaml_path}")
                raise ConfigError(f"Job type '{job_type}' must be a boolean in config file {config_yaml_path}")
            logger.debug(f"Job type '{job_type}' is valid.")

        date_filters = ['all time', 'month', 'week', '24 hours']
        for date_filter in date_filters:
            if not isinstance(parameters['date'].get(date_filter), bool):
                logger.error(f"Date filter '{date_filter}' must be a boolean in config file {config_yaml_path}")
                raise ConfigError(f"Date filter '{date_filter}' must be a boolean in config file {config_yaml_path}")
            logger.debug(f"Date filter '{date_filter}' is valid.")

        if not all(isinstance(pos, str) for pos in parameters['positions']):
            logger.error(f"'positions' must be a list of strings in config file {config_yaml_path}")
            raise ConfigError(f"'positions' must be a list of strings in config file {config_yaml_path}")
        logger.debug("'positions' list validated successfully.")

        if not all(isinstance(loc, str) for loc in parameters['locations']):
            logger.error(f"'locations' must be a list of strings in config file {config_yaml_path}")
            raise ConfigError(f"'locations' must be a list of strings in config file {config_yaml_path}")
        logger.debug("'locations' list validated successfully.")

        approved_distances = {0, 5, 10, 25, 50, 100}
        if parameters['distance'] not in approved_distances:
            logger.error(f"Invalid distance value in config file {config_yaml_path}. Must be one of: {approved_distances}")
            raise ConfigError(f"Invalid distance value in config file {config_yaml_path}. Must be one of: {approved_distances}")
        logger.debug(f"Distance value '{parameters['distance']}' is valid.")

        for blacklist in ['company_blacklist', 'title_blacklist']:
            if not isinstance(parameters.get(blacklist), list):
                logger.error(f"'{blacklist}' must be a list in config file {config_yaml_path}")
                raise ConfigError(f"'{blacklist}' must be a list in config file {config_yaml_path}")
            if parameters[blacklist] is None:
                parameters[blacklist] = []
                logger.warning(f"'{blacklist}' is None in config. Setting to empty list.")
            logger.debug(f"Blacklist '{blacklist}' validated successfully.")

        logger.info("Configuration file validated successfully.")
        return parameters

    @staticmethod
    def validate_secrets(env_path: Path = Path('.env')) -> str:
        logger.info(f"Validating secrets from environment file: {env_path}")
        load_dotenv(dotenv_path=env_path)
        mandatory_secrets = ['LLM_API_KEY']

        for secret in mandatory_secrets:
            value = os.getenv(secret)
            if value is None:
                logger.error(f"Missing environment variable '{secret}' in {env_path}.")
                raise ConfigError(f"Missing environment variable '{secret}' in {env_path}.")
            if not value.strip():
                logger.error(f"Environment variable '{secret}' cannot be empty in {env_path}.")
                raise ConfigError(f"Environment variable '{secret}' cannot be empty in {env_path}.")
            logger.debug(f"Environment variable '{secret}' is set.")

        logger.info("All required secrets are validated.")
        return os.getenv('LLM_API_KEY')

class FileManager:
    @staticmethod
    def find_file(name_containing: str, with_extension: str, at_path: Path) -> Path:
        logger.debug(f"Searching for file containing '{name_containing}' with extension '{with_extension}' in {at_path}")
        file = next(
            (
                file 
                for file in at_path.iterdir() 
                if name_containing.lower() in file.name.lower() and file.suffix.lower() == with_extension.lower()
            ), 
            None
        )
        if file:
            logger.debug(f"Found file: {file}")
        else:
            logger.warning(f"No file found containing '{name_containing}' with extension '{with_extension}' in {at_path}")
        return file

    @staticmethod
    def validate_data_folder(app_data_folder: Path) -> tuple:
        logger.info(f"Validating data folder at: {app_data_folder}")
        if not app_data_folder.exists() or not app_data_folder.is_dir():
            logger.error(f"Data folder not found: {app_data_folder}")
            raise FileNotFoundError(f"Data folder not found: {app_data_folder}")

        required_files = ['config.yaml', 'plain_text_resume.yaml']
        missing_files = [file for file in required_files if not (app_data_folder / file).exists()]
        
        if missing_files:
            logger.error(f"Missing files in the data folder: {', '.join(missing_files)}")
            raise FileNotFoundError(f"Missing files in the data folder: {', '.join(missing_files)}")
        
        logger.debug("All required files are present in the data folder.")
        output_folder = app_data_folder / 'output'
        output_folder.mkdir(exist_ok=True)
        logger.debug(f"Output folder is set at: {output_folder}")
        return (app_data_folder / 'config.yaml', app_data_folder / 'plain_text_resume.yaml', output_folder)

    @staticmethod
    def file_paths_to_dict(resume_file: Path | None, plain_text_resume_file: Path) -> dict:
        logger.debug(f"Converting file paths to dictionary. Resume file: {resume_file}, Plain text resume file: {plain_text_resume_file}")
        if not plain_text_resume_file.exists():
            logger.error(f"Plain text resume file not found: {plain_text_resume_file}")
            raise FileNotFoundError(f"Plain text resume file not found: {plain_text_resume_file}")

        result = {'plainTextResume': plain_text_resume_file}
        logger.debug("Added plainTextResume to file paths dictionary.")

        if resume_file:
            if not resume_file.exists():
                logger.error(f"Resume file not found: {resume_file}")
                raise FileNotFoundError(f"Resume file not found: {resume_file}")
            result['resume'] = resume_file
            logger.debug("Added resume to file paths dictionary.")

        return result

def init_browser() -> webdriver.Chrome:
    logger.info("Initializing browser.")
    try:
        options = chrome_browser_options()
        service = ChromeService(ChromeDriverManager().install())
        browser = webdriver.Chrome(service=service, options=options)
        logger.info("Browser initialized successfully.")
        return browser
    except WebDriverException as e:
        logger.exception("WebDriver failed to initialize.")
        raise RuntimeError(f"Failed to initialize browser: {str(e)}")

def create_and_run_bot(parameters, llm_api_key):
    logger.info("Creating and running the bot.")
    try:
        logger.debug("Initializing StyleManager and ResumeGenerator.")
        style_manager = StyleManager()
        resume_generator = ResumeGenerator()
        
        plain_text_path = parameters['uploads']['plainTextResume']
        logger.debug(f"Reading plain text resume from: {plain_text_path}")
        with open(plain_text_resume_file := plain_text_path, "r", encoding='utf-8') as file:
            plain_text_resume = file.read()
        logger.debug("Plain text resume read successfully.")
        
        logger.debug("Creating Resume object.")
        resume_object = Resume(plain_text_resume)
        logger.debug("Resume object created.")
        
        logger.debug("Initializing FacadeManager.")
        resume_generator_manager = FacadeManager(
            llm_api_key, 
            style_manager, 
            resume_generator, 
            resume_object, 
            Path("data_folder/output")
        )
        logger.debug("FacadeManager initialized.")
        
        logger.info("Clearing terminal screen.")
        os.system('cls' if os.name == 'nt' else 'clear')
        logger.debug("Choosing resume style.")
        resume_generator_manager.choose_style()
        os.system('cls' if os.name == 'nt' else 'clear')
        
        logger.debug("Creating JobApplicationProfile object.")
        job_application_profile_object = JobApplicationProfile(plain_text_resume)
        logger.debug("JobApplicationProfile object created.")
        
        logger.debug("Initializing browser for bot.")
        browser = init_browser()
        logger.debug("Browser initialized for bot.")
        
        logger.debug("Initializing bot components.")
        login_component = AIHawkAuthenticator(browser)
        apply_component = AIHawkJobManager(browser)
        gpt_answerer_component = GPTAnswerer(parameters, llm_api_key)
        logger.debug("Bot components initialized.")
        
        logger.debug("Setting up AIHawkBotFacade.")
        bot = AIHawkBotFacade(login_component, apply_component)
        bot.set_job_application_profile_and_resume(job_application_profile_object, resume_object)
        bot.set_gpt_answerer_and_resume_generator(gpt_answerer_component, resume_generator_manager)
        bot.set_parameters(parameters)
        logger.debug("AIHawkBotFacade setup complete.")
        
        logger.info("Starting bot login process.")
        bot.start_login()
        logger.info("Starting bot application process.")
        bot.start_apply()
        logger.info("Bot has finished running.")
    except WebDriverException as e:
        logger.exception("WebDriver error occurred while running the bot.")
    except ConfigError as ce:
        logger.exception("Configuration error occurred while running the bot.")
        raise ce
    except Exception as e:
        logger.exception("An unexpected error occurred while running the bot.")
        raise RuntimeError(f"Error running the bot: {str(e)}")

@click.command()
@click.option(
    '--resume', 
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path), 
    help="Path to the resume PDF file"
)
def main(resume: Path = None):
    """
    Main function that processes the resume and interacts with the LLM API.

    Args:
        resume (Path, optional): Path to the resume PDF file.
    """
    logger.info("Application started.")
    try:
        data_folder = Path("data_folder")
        logger.debug(f"Validating data folder: {data_folder}")
        config_file, plain_text_resume_file, output_folder = FileManager.validate_data_folder(data_folder)
        
        logger.debug("Validating configuration.")
        parameters = ConfigValidator.validate_config(config_file)
        
        logger.debug("Validating secrets.")
        llm_api_key = ConfigValidator.validate_secrets(Path('.env'))
        
        logger.debug("Setting up file uploads and output directory.")
        parameters['uploads'] = FileManager.file_paths_to_dict(resume, plain_text_resume_file)
        parameters['outputFileDirectory'] = output_folder
        
        logger.info("Starting bot creation and execution.")
        create_and_run_bot(parameters, llm_api_key)
    
    except ConfigError as ce:
        logger.exception("Configuration error encountered.")
        logger.error(
            "Refer to the configuration guide for troubleshooting: "
            "https://github.com/feder-cr/AIHawk_AIHawk_automatic_job_application/blob/main/readme.md#configuration"
        )
    except FileNotFoundError as fnf:
        logger.exception("File not found error encountered.")
        logger.error("Ensure all required files are present in the data folder.")
        logger.error(
            "Refer to the file setup guide: "
            "https://github.com/feder-cr/AIHawk_AIHawk_automatic_job_application/blob/main/readme.md#configuration"
        )
    except RuntimeError as re:
        logger.exception("Runtime error encountered.")
        logger.error(
            "Refer to the configuration and troubleshooting guide: "
            "https://github.com/feder-cr/AIHawk_AIHawk_automatic_job_application/blob/main/readme.md#configuration"
        )
    except Exception as e:
        logger.exception("An unexpected error occurred.")
        logger.error(
            "Refer to the general troubleshooting guide: "
            "https://github.com/feder-cr/AIHawk_AIHawk_automatic_job_application/blob/main/readme.md#configuration"
        )
    finally:
        logger.info("Application finished.")

if __name__ == "__main__":
    main()