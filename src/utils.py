import os
import random
import sys
import time
from pathlib import Path
from datetime import datetime
import json
import logging

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By

from loguru import logger

from app_config import MINIMUM_LOG_LEVEL

# Define log file path
LOG_FILE_PATH = Path("./log/app.log")

# Define allowed log levels
ALLOWED_LEVELS = ["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Class to intercept standard logging and redirect to Loguru
class InterceptHandler(logging.Handler):
    def emit(self, record):
        # Retrieve Loguru level
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = "INFO"
        # Get the log message
        message = record.getMessage()
        # Log via Loguru
        logger.log(level, message)

def configure_logging():
    # Remove default Loguru handlers to prevent duplicate logs
    logger.remove()

    # Validate and set minimum log level for the log file
    if MINIMUM_LOG_LEVEL in ALLOWED_LEVELS:
        file_log_level = MINIMUM_LOG_LEVEL
    else:
        file_log_level = "WARNING"
        logger.warning(f"Invalid MINIMUM_LOG_LEVEL: {MINIMUM_LOG_LEVEL}. Defaulting to WARNING.")

    # Add Loguru handler for terminal (INFO and above)
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        enqueue=True
    )

    # Add Loguru handler for log file (MINIMUM_LOG_LEVEL and above)
    logger.add(
        LOG_FILE_PATH,
        level=file_log_level,
        rotation="100 MB",
        retention="1 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        enqueue=True
    )

    # Intercept standard logging and redirect to Loguru
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.WARNING)

    # Set specific library log levels to WARNING to reduce noise
    logging.getLogger("WDM").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    logger.debug(f"Logging configured. Logs at level {file_log_level} and above are saved to {LOG_FILE_PATH}.")
    logger.info("INFO level and above are displayed in the terminal.")

configure_logging()

chrome_profile_path = os.path.join(os.getcwd(), "chrome_profile", "linkedin_profile")

def ensure_chrome_profile():
    logger.debug(f"Ensuring Chrome profile exists at path: {chrome_profile_path}")
    profile_dir = os.path.dirname(chrome_profile_path)
    try:
        if not os.path.exists(profile_dir):
            os.makedirs(profile_dir)
            logger.debug(f"Created directory for Chrome profile: {profile_dir}")
        if not os.path.exists(chrome_profile_path):
            os.makedirs(chrome_profile_path)
            logger.debug(f"Created Chrome profile directory: {chrome_profile_path}")
    except Exception as e:
        logger.error(f"Failed to ensure Chrome profile directories: {e}", exc_info=True)
        raise
    return chrome_profile_path

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

def chrome_browser_options():
    logger.debug("Setting Chrome browser options")
    ensure_chrome_profile()
    options = webdriver.ChromeOptions()
    
    # Headless mode
    # options.add_argument("--headless")
    
    # Specify the absolute path to the Chrome binary
    options.binary_location = '/usr/bin/google-chrome'
    
    # Existing options
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("window-size=1200x800")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-translate")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-autofill")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-animations")
    options.add_argument("--disable-cache")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])

    # Additional flags for stability
    options.add_argument("--disable-setuid-sandbox")
    # options.add_argument("--disable-software-rasterizer")
    options.add_argument("--no-zygote")
    options.add_argument("--single-process")
    options.add_argument("--remote-debugging-port=9222")

    # Preferences to optimize loading
    prefs = {
        "profile.default_content_setting_values.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
    }
    options.add_experimental_option("prefs", prefs)

    # Chrome profile configuration
    if chrome_profile_path:
        initial_path = os.path.dirname(chrome_profile_path)
        profile_dir = os.path.basename(chrome_profile_path)
        options.add_argument(f'--user-data-dir={initial_path}')
        options.add_argument(f"--profile-directory={profile_dir}")
        logger.debug(f"Using Chrome profile directory: {chrome_profile_path}")
    else:
        options.add_argument("--incognito")
        logger.debug("Using Chrome in incognito mode")

    return options
    
def write_to_file(job, file_name):
    logger.debug(f"Writing job application result to file: '{file_name}'.")
    pdf_path = Path(job.pdf_path).resolve()
    pdf_path = pdf_path.as_uri()
    
    # Get current date and time
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    data = {
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "link": job.link,
        "apply_method": job.apply_method,
        "state": job.state,
        "salary": job.salary,
        # "description": job.description,
        # "summarize_job_description": job.summarize_job_description,	
        "pdf_path": pdf_path,
        "recruiter_link": job.recruiter_link,
        "search_term": job.position,
        "score": job.score,  
        "timestamp": current_time
    }
    
    file_path = Path("data_folder") / "output" / f"{file_name}.json"
    
    if not file_path.exists():
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump([data], f, indent=4)
            logger.debug(f"Job data written to new file: '{file_name}'.")
        except Exception as e:
            logger.error(f"Failed to write to new file '{file_name}': {e}", exc_info=True)
    else:
        try:
            with open(file_path, 'r+', encoding='utf-8') as f:
                try:
                    existing_data = json.load(f)
                except json.JSONDecodeError:
                    logger.error(f"JSON decode error in file: {file_path}. Initializing with empty list.")
                    existing_data = []
                
                existing_data.append(data)
                f.seek(0)
                json.dump(existing_data, f, indent=4)
                f.truncate()
            logger.debug(f"Job data appended to existing file: '{file_name}'.")
        except Exception as e:
            logger.error(f"Failed to append to file '{file_name}': {e}", exc_info=True)

def capture_screenshot(driver,name: str) -> None:
    """
    Captures a screenshot of the current browser window.
    """
    try:
        screenshots_dir = "screenshots"
        ensure_directory(screenshots_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(screenshots_dir, f"{timestamp}_{name}.png")
        success = driver.save_screenshot(file_path)
        if success:
            logger.debug(f"Screenshot saved at: {file_path}")
        else:
            logger.warning("Failed to save screenshot")
    except Exception as e:
        logger.error("An error occurred while capturing the screenshot", exc_info=True)

def ensure_directory(folder_path: str) -> None:
    """
    Ensures that the specified directory exists.
    """
    try:
        os.makedirs(folder_path, exist_ok=True)
        logger.debug(f"Directory ensured at path: {folder_path}")
    except Exception as e:
        logger.error(f"Failed to create directory: {folder_path}", exc_info=True)
        raise