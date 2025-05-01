# src/utils.py
"""
General utility functions for the web automation bot.

Includes logging configuration, browser setup helpers, file/directory operations,
and Selenium interaction utilities like scrolling and screenshotting.
"""
import re
import os
import random
import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Union

# Third-party Imports
from loguru import logger
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException, StaleElementReferenceException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions # Import Options directly


# --- Configuration Defaults (Can be overridden by environment variables) ---
DEFAULT_LOG_DIR = Path("./logs")
DEFAULT_LOG_FILENAME = "automation_run.log"
DEFAULT_CONSOLE_LOG_LEVEL = "INFO"
DEFAULT_FILE_LOG_LEVEL = "DEBUG"
DEFAULT_SCREENSHOT_DIR = Path("./screenshots")
DEFAULT_CHROME_PROFILE_DIR = Path("./chrome_profile/default_user") # Generic name

# --- Logging Setup ---

# Allowed log levels for validation
ALLOWED_LOG_LEVELS = ["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]

class InterceptHandler(logging.Handler):
    """Intercepts standard logging messages and redirects them to Loguru."""
    def emit(self, record: logging.LogRecord):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno # Keep original level number if mapping fails
        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

def configure_logging():
    """
    Configures Loguru for console and file logging.

    Reads log levels from environment variables (CONSOLE_LOG_LEVEL, FILE_LOG_LEVEL)
    with defaults. Intercepts standard Python logging.
    """
    # Determine log levels from environment or use defaults
    console_level = os.getenv("CONSOLE_LOG_LEVEL", DEFAULT_CONSOLE_LOG_LEVEL).upper()
    file_level = os.getenv("FILE_LOG_LEVEL", DEFAULT_FILE_LOG_LEVEL).upper()

    # Validate levels
    if console_level not in ALLOWED_LOG_LEVELS:
        print(f"Warning: Invalid CONSOLE_LOG_LEVEL '{console_level}'. Defaulting to '{DEFAULT_CONSOLE_LOG_LEVEL}'.", file=sys.stderr)
        console_level = DEFAULT_CONSOLE_LOG_LEVEL
    if file_level not in ALLOWED_LOG_LEVELS:
        print(f"Warning: Invalid FILE_LOG_LEVEL '{file_level}'. Defaulting to '{DEFAULT_FILE_LOG_LEVEL}'.", file=sys.stderr)
        file_level = DEFAULT_FILE_LOG_LEVEL

    # Ensure log directory exists
    log_dir = DEFAULT_LOG_DIR
    log_file_path = log_dir / DEFAULT_LOG_FILENAME
    try:
         log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
         print(f"Error: Could not create log directory {log_dir}: {e}", file=sys.stderr)
         # Decide: exit or continue without file logging? Continuing for now.
         file_level = "CRITICAL" # Effectively disable file logging if dir fails


    # Configure Loguru
    logger.remove() # Remove default handler

    # Console Handler
    logger.add(
        sys.stderr, # Log to stderr for better compatibility with pipelines/redirection
        level=console_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>",
        colorize=True,
        enqueue=True # Make logging calls non-blocking
    )

    # File Handler (only if directory creation succeeded implicitly)
    try:
         logger.add(
             log_file_path,
             level=file_level,
             rotation="100 MB", # Rotate when file reaches 100MB
             retention="14 days", # Keep logs for 14 days
             compression="zip", # Compress rotated logs
             format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {process} | {name}:{function}:{line} - {message}",
             enqueue=True, # Make logging calls non-blocking
             # serialize=True # Optional: Log as JSON objects
         )
         logger.info(f"File logging configured at level {file_level} to {log_file_path}")
    except Exception as e:
         logger.error(f"Failed to configure file logging to {log_file_path}: {e}")


    # Intercept standard logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0) # Capture all levels, Loguru filters them
    # Set levels for noisy libraries
    noisy_loggers = ["webdriver_manager", "selenium.webdriver.remote.remote_connection", "urllib3.connectionpool"]
    for log_name in noisy_loggers:
         logging.getLogger(log_name).setLevel(logging.WARNING)

    logger.info(f"Logging configured. Console level: {console_level}. File level: {file_level}.")

# Call configuration immediately upon import
# configure_logging() # Note: Calling this here might interfere with tests or other setup.
# It's often better to call configure_logging() explicitly in the main application entry point (main.py).
# If called here, ensure environment variables are set *before* this module is imported.


# --- Directory & File Utils ---

def ensure_directory(dir_path: Union[str, Path]) -> Optional[Path]:
    """
    Ensures that the specified directory exists, creating it if necessary.

    Args:
        dir_path (Union[str, Path]): The path to the directory.

    Returns:
        Optional[Path]: The Path object of the directory if successful, None otherwise.
    """
    try:
        path = Path(dir_path)
        path.mkdir(parents=True, exist_ok=True)
        logger.trace(f"Directory ensured: {path.resolve()}")
        return path
    except OSError as e:
        logger.error(f"Failed to create or access directory: {dir_path} - {e}", exc_info=True)
        return None
    except Exception as e: # Catch other potential errors like permission issues
        logger.error(f"Unexpected error ensuring directory {dir_path}: {e}", exc_info=True)
        return None


# --- Chrome Profile & Options ---

def ensure_chrome_profile(profile_dir: Path = DEFAULT_CHROME_PROFILE_DIR) -> Optional[Path]:
    """
    Ensures the Chrome profile directory structure exists.

    Args:
        profile_dir (Path): The desired path for the Chrome profile directory.
                            Defaults to DEFAULT_CHROME_PROFILE_DIR.

    Returns:
        Optional[Path]: The profile directory Path object if successful, None otherwise.
    """
    logger.debug(f"Ensuring Chrome profile directory exists at: {profile_dir}")
    return ensure_directory(profile_dir)


def chrome_browser_options(
    headless: bool = False,
    profile_path: Optional[Path] = None,
    binary_location: Optional[str] = None
) -> ChromeOptions:
    """
    Configures and returns Selenium ChromeOptions.

    Args:
        headless (bool): Whether to run Chrome in headless mode. Defaults to False.
                         Reads HEADLESS=true from env var as override.
        profile_path (Optional[Path]): Path to the Chrome user profile directory.
                                       If None, uses default or runs incognito.
                                       Reads CHROME_PROFILE_PATH from env var as override.
        binary_location (Optional[str]): Path to the Chrome executable. If None, uses system default.
                                         Reads CHROME_BINARY_PATH from env var as override.

    Returns:
        ChromeOptions: Configured options object for Chrome WebDriver.
    """
    logger.debug("Configuring Chrome browser options...")

    # Read overrides from environment variables
    headless_env = os.getenv("HEADLESS", str(headless)).lower() == 'true'
    profile_path_env = os.getenv("CHROME_PROFILE_PATH")
    binary_location_env = os.getenv("CHROME_BINARY_PATH")

    # Prioritize environment variables over arguments
    run_headless = headless_env
    profile_to_use = Path(profile_path_env) if profile_path_env else profile_path
    binary_to_use = binary_location_env if binary_location_env else binary_location

    options = ChromeOptions()

    # Headless Mode
    if run_headless:
        logger.info("Headless mode enabled.")
        options.add_argument("--headless=new") # Use new headless mode
        options.add_argument("--disable-gpu") # Often needed for headless
        options.add_argument("window-size=1920,1080") # Specify window size for headless
    else:
         logger.info("Running in headed mode.")
         options.add_argument("--start-maximized")

    # Binary Location (Use only if specified, otherwise let WebDriverManager find it)
    if binary_to_use:
        binary_path = Path(binary_to_use)
        if binary_path.is_file():
            logger.info(f"Using custom Chrome binary location: {binary_path}")
            options.binary_location = str(binary_path)
        else:
            logger.warning(f"Specified Chrome binary location not found: {binary_path}. Using default.")

    # Common options for stability and automation friendliness
    options.page_load_strategy = 'eager'
    options.add_argument("--no-sandbox") # Essential for Linux/Docker environments
    options.add_argument("--disable-dev-shm-usage") # Essential for Docker environments
    options.add_argument("--ignore-certificate-errors") # Useful for some environments
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-translate")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-logging") # Suppress console logs from Chrome itself
    options.add_argument("--log-level=3") # Set Chrome's internal log level to suppress info/warnings
    # options.add_argument("--disable-gpu") # Already added for headless, might help in headed too?

    # Experimental options to potentially reduce detection and resource usage
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    # options.add_experimental_option('useAutomationExtension', False)
    prefs = {
        "profile.default_content_setting_values.images": 2,          # Disable images
        "profile.managed_default_content_settings.stylesheets": 2,   # Disable CSS (might break sites) - use with caution
        "profile.default_content_setting_values.cookies": 1,         # Allow cookies (needed for login)
        "profile.default_content_setting_values.javascript": 1,      # Allow JS (essential)
        "profile.default_content_setting_values.plugins": 2,         # Disable plugins
        "profile.default_content_setting_values.popups": 2,          # Disable popups
        "profile.default_content_setting_values.geolocation": 2,     # Disable geolocation
        "profile.default_content_setting_values.notifications": 2,   # Disable notifications
        "credentials_enable_service": False,                         # Disable password saving prompt
        "profile.password_manager_enabled": False                    # Disable password manager
    }
    options.add_experimental_option("prefs", prefs)

    # User Agent Spoofing (Optional - use with caution)
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36"
    options.add_argument(f'user-agent={user_agent}')

    # Chrome Profile Configuration
    if profile_to_use:
        profile_dir_status = ensure_chrome_profile(profile_to_use)
        if profile_dir_status:
            # Need user-data-dir (parent) and profile-directory (basename)
            user_data_dir = str(profile_to_use.parent.resolve())
            profile_directory_name = profile_to_use.name
            options.add_argument(f"--user-data-dir={user_data_dir}")
            options.add_argument(f"--profile-directory={profile_directory_name}")
            logger.info(f"Using Chrome profile: UserDataDir='{user_data_dir}', Profile='{profile_directory_name}'")
        else:
             logger.warning(f"Failed to ensure profile directory '{profile_to_use}'. Using default profile or incognito.")
             # Fallback might be needed here depending on desired behavior
    else:
        # options.add_argument("--incognito") # Incognito might interfere with logins/state
        logger.debug("No specific Chrome profile path provided. Using default profile.")

    logger.debug("Chrome options configured.")
    return options


def capture_screenshot(driver: WebDriver, name_prefix: str) -> Optional[Path]:
    """
    Captures a screenshot of the current browser window, saving it with a timestamp.

    Args:
        driver (WebDriver): The Selenium WebDriver instance.
        name_prefix (str): A prefix for the screenshot filename (e.g., "error_login").

    Returns:
        Optional[Path]: The Path object of the saved screenshot, or None on failure.
    """
    screenshot_dir = ensure_directory(DEFAULT_SCREENSHOT_DIR)
    if not screenshot_dir:
         logger.error("Cannot save screenshot, screenshot directory setup failed.")
         return None

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3] # Add milliseconds
        # Sanitize prefix for filename
        safe_prefix = re.sub(r'[^\w\-]+', '_', name_prefix)
        filename = f"{safe_prefix}_{timestamp}.png"
        file_path = screenshot_dir / filename

        if driver.save_screenshot(str(file_path)):
            logger.info(f"Screenshot saved: {file_path}")
            return file_path
        else:
            logger.warning(f"Failed to save screenshot to {file_path} (driver returned false).")
            return None
    except WebDriverException as e:
        # Handle cases where driver might be closed or unresponsive
        logger.error(f"WebDriverException capturing screenshot '{name_prefix}': {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error capturing screenshot '{name_prefix}': {e}", exc_info=True)
        return None


def is_scrollable(element):
    """Utility function to determine if an element is scrollable."""
    try:
        scroll_height = int(element.get_attribute("scrollHeight"))
        client_height = int(element.get_attribute("clientHeight"))
        scrollable = scroll_height > client_height
        logger.debug(f"Element scrollable check: scrollHeight={scroll_height}, clientHeight={client_height}, scrollable={scrollable}")
        return scrollable
    except Exception as e:
        logger.error(f"Error determining scrollability: {e}", exc_info=True)
        return False


def scroll_slow(driver, scrollable_element, start=0, end=3600, step=300, reverse=False, max_attempts=10):
    logger.debug("Starting scroll_slow.")

    if step <= 0:
        logger.error("Step value must be positive.")
        raise ValueError("Step must be positive.")

    # Add explicit wait before checking if the element is scrollable
    try:
        WebDriverWait(driver, 10).until(EC.visibility_of(scrollable_element))
    except Exception as e:
        logger.error("Scrollable element is not visible: %s", e)
        return

    if not is_scrollable(scrollable_element):
        logger.warning("The element is not scrollable.")
        return

    script_scroll_to = "arguments[0].scrollTop = arguments[1];"

    try:
        # Ensure the element is visible
        if not scrollable_element.is_displayed():
            logger.warning("The element is not visible. Attempting to scroll it into view.")
            try:
                driver.execute_script("arguments[0].scrollIntoView(true);", scrollable_element)
                time.sleep(1)  # Wait for the element to become visible
                if not scrollable_element.is_displayed():
                    logger.error("The element is still not visible after attempting to scroll into view.")
                    return
                else:
                    logger.debug("Element is now visible after scrolling into view.")
            except Exception as e:
                logger.error(f"Failed to scroll the element into view: {e}", exc_info=True)
                return

        # Determine initial scroll positions
        scroll_height = int(scrollable_element.get_attribute("scrollHeight"))
        client_height = int(scrollable_element.get_attribute("clientHeight"))
        max_scroll_position = scroll_height - client_height

        logger.debug(f"Scroll height: {scroll_height}, Client height: {client_height}, Max scroll position: {max_scroll_position}")

        # Set scrolling direction
        if reverse:
            step = -abs(step)
            end_position = 0
            logger.debug("Configured to scroll upwards to the top.")
        else:
            step = abs(step)
            end_position = max_scroll_position
            logger.debug("Configured to scroll downwards to the bottom.")

        attempts = 0
        last_scroll_height = scroll_height
        current_scroll_position = int(float(scrollable_element.get_attribute("scrollTop") or 0))
        logger.debug(f"Initial scroll position: {current_scroll_position}")

        while True:
            # Calculate new scroll position
            new_scroll_position = current_scroll_position + step
            if reverse:
                if new_scroll_position <= end_position:
                    new_scroll_position = end_position
            else:
                if new_scroll_position >= end_position:
                    new_scroll_position = end_position

            # Execute the scroll
            driver.execute_script(script_scroll_to, scrollable_element, new_scroll_position)
            logger.debug(f"Scrolled to position: {new_scroll_position}")

            # Wait after each scroll
            time.sleep(random.uniform(0.2, 0.5))  # Wait time for new content to load

            # Update current scroll position
            current_scroll_position = int(float(scrollable_element.get_attribute("scrollTop") or 0))
            logger.debug(f"Current scrollTop after scrolling: {current_scroll_position}")

            if reverse:
                if current_scroll_position <= end_position:
                    logger.debug("Reached the top of the element.")
                    break
            else:
                # Check for new content
                new_scroll_height = int(scrollable_element.get_attribute("scrollHeight") or 0)
                logger.debug(f"New scroll height: {new_scroll_height}")

                if new_scroll_height > last_scroll_height:
                    logger.debug("New content detected. Updating end_position.")
                    last_scroll_height = new_scroll_height
                    end_position = new_scroll_height - client_height
                    attempts = 0
                else:
                    attempts += 1
                    logger.debug(f"No new content loaded. Attempt {attempts}/{max_attempts}.")
                    if attempts >= max_attempts:
                        logger.debug("Maximum scroll attempts reached. Ending scroll.")
                        break

                if current_scroll_position >= end_position:
                    logger.debug("Reached the bottom of the element.")
                    time.sleep(random.uniform(1.0, 1.5))
                    break

        # Ensure the final scroll position is correct
        driver.execute_script(script_scroll_to, scrollable_element, end_position)
        logger.debug(f"Scrolled to final position: {end_position}")

    except Exception as e:
        logger.error(f"An error occurred during scrolling: {e}", exc_info=True)
    logger.debug("Completed scroll_slow.")