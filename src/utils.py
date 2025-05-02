# src/utils.py
"""
General utility functions for the web automation bot.

Includes logging configuration, browser setup helpers, file/directory operations,
and Selenium interaction utilities like scrolling, screenshotting, and anti-detection enhancements.
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
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException,
    StaleElementReferenceException, ElementNotInteractableException
)
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
# Anti-detection Enhancement: Fake User-Agent
try:
    from fake_useragent import UserAgent
    _has_fake_useragent = True
except ImportError:
    logger.warning("`fake-useragent` not installed. Falling back to a default User-Agent. "
                   "Install with: pip install fake-useragent")
    _has_fake_useragent = False


# --- Configuration Defaults (Can be overridden by environment variables) ---
DEFAULT_LOG_DIR = Path("./logs")
DEFAULT_LOG_FILENAME = "automation_run.log"
DEFAULT_CONSOLE_LOG_LEVEL = "INFO"
DEFAULT_FILE_LOG_LEVEL = "DEBUG"
DEFAULT_SCREENSHOT_DIR = Path("./screenshots")
DEFAULT_CHROME_PROFILE_DIR = Path("./chrome_profile/default_user") # Generic name
DEFAULT_BROWSER_LANGUAGE = "en-US,en;q=0.9" # Default language

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
        # Handle potential None frames
        while frame and frame.f_code.co_filename == logging.__file__:
             # Check if frame.f_back exists before accessing it
            if frame.f_back:
                frame = frame.f_back
                depth += 1
            else:
                 # Break if there's no previous frame (shouldn't happen in normal logging)
                 break
        # Ensure frame is not None before proceeding
        if frame:
            logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())
        else:
            # Fallback if frame becomes None unexpectedly
             logger.opt(exception=record.exc_info).log(level, record.getMessage())


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
    noisy_loggers = ["webdriver_manager", "selenium.webdriver.remote.remote_connection", "urllib3.connectionpool", "hpack"]
    for log_name in noisy_loggers:
         logging.getLogger(log_name).setLevel(logging.WARNING)

    logger.info(f"Logging configured. Console level: {console_level}. File level: {file_level}.")

# Call configuration explicitly in your main application entry point (e.g., main.py)
# configure_logging()


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
    binary_location: Optional[str] = None,
    proxy: Optional[str] = None # New parameter for proxy
) -> ChromeOptions:
    """
    Configures and returns ChromeOptions for the WebDriver, including anti-detection measures.

    Args:
        headless (bool): Run in headless mode. Defaults to False.
                         Forced to True if DISPLAY environment variable is not set.
        profile_path (Optional[Path]): Path to the persistent user profile directory.
        binary_location (Optional[str]): Path to a custom Chrome binary.
        proxy (Optional[str]): Proxy server string (e.g., "http://user:pass@host:port" or "socks5://host:port").

    Returns:
        ChromeOptions: Configured options object.
    """
    logger.debug("Configuring Chrome browser options with anti-detection enhancements…")

    options = ChromeOptions()

    # --- Determine settings from environment variables or parameters ---
    # Headless mode check (forced if no display)
    env_headless = os.getenv("HEADLESS", str(headless)).lower() == "true"
    if not os.getenv("DISPLAY") and not env_headless:
        logger.info("DISPLAY environment variable not set - forcing headless mode.")
        env_headless = True

    # Profile path
    env_profile = Path(os.getenv("CHROME_PROFILE_PATH")) if os.getenv("CHROME_PROFILE_PATH") else profile_path

    # Binary path
    env_binary = os.getenv("CHROME_BINARY_PATH") or binary_location

    # Browser Language
    env_lang = os.getenv("BROWSER_LANG", DEFAULT_BROWSER_LANGUAGE)

    # --- Apply Options ---

    # Headless or Headed
    if env_headless:
        logger.info("Headless mode enabled.")
        options.add_argument("--headless=new") # Use the new, more stealthy headless mode
        options.add_argument("--disable-gpu") # Often needed for headless
        options.add_argument("--window-size=1920,1080") # Use a common desktop resolution
    else:
        # Start maximized for a more natural appearance in headed mode
        options.add_argument("--start-maximized")

    # Custom Binary Path
    if env_binary:
        if Path(env_binary).exists():
             options.binary_location = str(env_binary)
             logger.info(f"Using custom Chrome binary at: {env_binary}")
        else:
             logger.warning(f"Custom Chrome binary path specified but not found: {env_binary}. Using default.")


    # Common Arguments for Stability and Stealth
    options.page_load_strategy = "eager" # Load faster, interact sooner (can be 'normal' too)
    options.add_argument("--no-sandbox") # Often required in containerized environments
    options.add_argument("--disable-dev-shm-usage") # Overcomes resource limits in Docker/Linux
    options.add_argument("--disable-blink-features=AutomationControlled") # Another way to hide automation
    options.add_argument("--ignore-certificate-errors") # Handle potential SSL issues (use carefully)
    options.add_argument("--disable-extensions") # Avoid interference from extensions
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-translate") # Disable Google Translate popup
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-logging") # Reduce browser's own logging
    options.add_argument("--log-level=3") # Set Chrome's internal log level to FATAL

    # Crucial Anti-Detection Flags
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)

    # User-Agent Spoofing (Dynamic)
    if _has_fake_useragent:
        try:
            ua = UserAgent()
            random_ua = ua.chrome # Get a random Chrome UA
            options.add_argument(f'user-agent={random_ua}')
            logger.info(f"Using dynamic User-Agent: {random_ua}")
        except Exception as ua_error:
            logger.warning(f"Failed to get dynamic User-Agent using fake-useragent: {ua_error}. Using a default.")
            # Fallback to a recent, common UA if fake-useragent fails
            options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36') # Update Chrome version periodically
    else:
        # Fallback if fake-useragent is not installed
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36') # Update Chrome version periodically

    # Browser Language
    options.add_argument(f"--lang={env_lang}")
    logger.info(f"Setting browser language: {env_lang}")

    # WebRTC IP Leak Prevention (Optional, can sometimes interfere)
    # prefs["profile.default_content_setting_values.webrtc_ip_handling_policy"] = "disable_non_proxied_udp"

    # Realistic Browser Preferences
    prefs = {
        # Enable images and stylesheets to appear more human
        "profile.default_content_setting_values.images": 1,
        "profile.managed_default_content_settings.stylesheets": 1,
        # Essential settings
        "profile.default_content_setting_values.cookies": 1,
        "profile.default_content_setting_values.javascript": 1,
        # Disable things that might cause popups or inconsistencies
        "profile.default_content_setting_values.plugins": 2, # Disable plugins
        "profile.default_content_setting_values.popups": 2, # Disable popups
        "profile.default_content_setting_values.geolocation": 2, # Disable geolocation prompt
        "profile.default_content_setting_values.notifications": 2, # Disable notifications prompt
        # Security/Privacy related
        "credentials_enable_service": False, # Disable Chrome's password saving prompt
        "profile.password_manager_enabled": False, # Disable password manager
        "download.prompt_for_download": False, # Disable download prompt, handle downloads programmatically if needed
        "download.directory_upgrade": True,
        # "safeBrowse.enabled": True, # Keep Safe Browse enabled for realism? Or disable? Test needed.
    }
    options.add_experimental_option("prefs", prefs)

    # Persistent Profile (Crucial for sessions, cookies, mimicking returning user)
    if env_profile:
        profile_dir_to_ensure = Path(env_profile)
        if ensure_chrome_profile(profile_dir_to_ensure):
            # Note: user-data-dir should be the *parent* directory of the profile folder
            user_data_dir = profile_dir_to_ensure.parent.resolve()
            profile_directory_name = profile_dir_to_ensure.name
            options.add_argument(f"--user-data-dir={user_data_dir}")
            options.add_argument(f"--profile-directory={profile_directory_name}")
            logger.info(f"Using Chrome profile: Name='{profile_directory_name}', Parent Dir='{user_data_dir}'")
        else:
            logger.error(f"Failed to ensure profile directory {env_profile}. Profile will not be persistent.")



    # Advanced Anti-Detection (Commented out - use with caution)
    # Some sites check navigator.webdriver; this attempts to override it after load.
    # You would execute this script via driver.execute_script(...) after page load.
    # logger.debug("Note: To further hide automation, consider executing JS after page load: "
    #             "\"Object.defineProperty(navigator, 'webdriver', {get: () => undefined})\"")

    logger.debug("Chrome browser options configured.")
    return options

# --- Selenium Interaction Utilities ---

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

def is_scrollable(driver: WebDriver, element: WebElement) -> bool:
    """Utility function to determine if an element is scrollable using JS."""
    try:
        # Use JavaScript for a more reliable check across browser versions
        return driver.execute_script(
            "return arguments[0].scrollHeight > arguments[0].clientHeight;",
            element
        )
    except StaleElementReferenceException:
        logger.warning("Stale element reference encountered while checking scrollability.")
        return False
    except Exception as e:
        logger.error(f"Error determining scrollability via JS: {e}", exc_info=False)
        # Fallback attempt using attributes (less reliable)
        try:
            scroll_height = int(element.get_attribute("scrollHeight") or 0)
            client_height = int(element.get_attribute("clientHeight") or 0)
            scrollable = scroll_height > client_height
            logger.trace(f"Scrollability fallback check: scrollH={scroll_height}, clientH={client_height}, scrollable={scrollable}")
            return scrollable
        except Exception as fallback_e:
            logger.error(f"Fallback scrollability check also failed: {fallback_e}", exc_info=False)
            return False

def scroll_slow(driver: WebDriver, scrollable_element: WebElement, direction: str = "down", max_attempts: int = 5) -> None:
    """
    Scrolls an element smoothly, mimicking human behavior with random pauses.
    Handles dynamically loading content.

    Args:
        driver (WebDriver): The Selenium WebDriver instance.
        scrollable_element (WebElement): The element to scroll within.
        direction (str): "down" to scroll to bottom, "up" to scroll to top. Defaults to "down".
        max_attempts (int): Max consecutive scrolls without detecting new content (for direction="down").
    """
    logger.debug(f"Starting smooth scroll, direction: {direction}")

    try:
        # Wait for element visibility
        WebDriverWait(driver, 10).until(EC.visibility_of(scrollable_element))
    except TimeoutException:
        logger.error("Scrollable element did not become visible.")
        capture_screenshot(driver, "scroll_element_not_visible")
        return
    except Exception as e:
        logger.error(f"Unexpected error waiting for scrollable element visibility: {e}", exc_info=True)
        return

    if not is_scrollable(driver, scrollable_element):
        logger.info("Element is not scrollable.")
        return

    attempts_without_new_content = 0
    last_scroll_height = driver.execute_script("return arguments[0].scrollHeight", scrollable_element)
    client_height = driver.execute_script("return arguments[0].clientHeight", scrollable_element)

    script_scroll_by = "arguments[0].scrollTop += arguments[1];"
    script_scroll_to_top = "arguments[0].scrollTop = 0;"
    script_scroll_to_bottom = "arguments[0].scrollTop = arguments[0].scrollHeight;"

    if direction == "up":
        logger.debug("Scrolling to top.")
        driver.execute_script(script_scroll_to_top, scrollable_element)
        time.sleep(random.uniform(0.3, 0.7)) # Pause after reaching top
        logger.debug("Finished scrolling up.")
        return

    # --- Scrolling Down Logic ---
    logger.debug("Scrolling down...")
    while True:
        # Scroll down by a random fraction of the client height
        scroll_amount = int(client_height * random.uniform(0.6, 0.9))
        driver.execute_script(script_scroll_by, scrollable_element, scroll_amount)

        # Random pause mimicking human reading/viewing time
        time.sleep(random.uniform(0.4, 1.0))

        # Check current scroll position and height
        current_scroll_top = driver.execute_script("return arguments[0].scrollTop", scrollable_element)
        new_scroll_height = driver.execute_script("return arguments[0].scrollHeight", scrollable_element)

        # Check if new content loaded
        if new_scroll_height > last_scroll_height:
            logger.trace(f"New content loaded. Old height: {last_scroll_height}, New height: {new_scroll_height}")
            last_scroll_height = new_scroll_height
            attempts_without_new_content = 0 # Reset counter
        else:
            attempts_without_new_content += 1
            logger.trace(f"No new content detected. Attempt {attempts_without_new_content}/{max_attempts}")

        # Check termination conditions
        # 1. Reached the bottom (with a small tolerance)
        if current_scroll_top + client_height >= last_scroll_height - 10: # Tolerance for rounding
            logger.debug("Reached or very near bottom of the scrollable element.")
            # Optional: Scroll exactly to bottom just in case
            driver.execute_script(script_scroll_to_bottom, scrollable_element)
            time.sleep(random.uniform(0.2, 0.5))
            break

        # 2. Max attempts without new content reached
        if attempts_without_new_content >= max_attempts:
            logger.debug(f"Max scroll attempts ({max_attempts}) without new content reached. Stopping scroll.")
            # Optional: Scroll exactly to bottom
            driver.execute_script(script_scroll_to_bottom, scrollable_element)
            time.sleep(random.uniform(0.2, 0.5))
            break

    logger.debug("Finished scrolling down.")


def type_like_human(element: WebElement, text: str, min_delay: float = 0.05, max_delay: float = 0.18) -> None:
    """
    Sends keys to an element character by character with random delays, mimicking human typing.

    Args:
        element (WebElement): The input element to type into.
        text (str): The text to type.
        min_delay (float): Minimum delay between characters in seconds.
        max_delay (float): Maximum delay between characters in seconds.
    """
    logger.trace(f"Typing text like human: '{text[:20]}...' into element {element.tag_name}")
    for char in text:
        try:
            element.send_keys(char)
            time.sleep(random.uniform(min_delay, max_delay))
        except ElementNotInteractableException:
            logger.error(f"Element {element.tag_name} not interactable while trying to type '{char}'. Stopping typing.")
            capture_screenshot(element.parent, f"typing_error_not_interactable") # element.parent is WebDriver
            raise # Re-raise the exception so the caller knows typing failed
        except StaleElementReferenceException:
             logger.error(f"Element {element.tag_name} became stale while typing '{char}'. Stopping typing.")
             capture_screenshot(element.parent, f"typing_error_stale")
             raise
        except Exception as e:
             logger.error(f"Unexpected error typing character '{char}': {e}", exc_info=True)
             capture_screenshot(element.parent, f"typing_error_unexpected")
             raise
    logger.trace("Finished typing like human.")