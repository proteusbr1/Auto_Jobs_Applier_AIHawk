import os
import random
import sys
import time

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from loguru import logger

from app_config import MINIMUM_LOG_LEVEL

log_file = "app_log.log"

# Define allowed log levels
allowed_levels = ["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Configure logger based on MINIMUM_LOG_LEVEL
def configure_logger():
    if MINIMUM_LOG_LEVEL in allowed_levels:
        level = MINIMUM_LOG_LEVEL
    else:
        level = "DEBUG"
        logger.warning(f"Invalid log level: {MINIMUM_LOG_LEVEL}. Defaulting to DEBUG.")
    
    logger.remove()
    
    # Add stderr with detailed format
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        enqueue=True
    )
    
    # Add file handler with DEBUG level and detailed format
    logger.add(
        log_file,
        level="DEBUG",
        rotation="10 MB",
        retention="10 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        enqueue=True
    )

configure_logger()

chrome_profile_path = os.path.join(os.getcwd(), "chrome_profile", "linkedin_profile")

def ensure_chrome_profile():
    logger.debug(f"Ensuring Chrome profile exists at path: {chrome_profile_path}")
    profile_dir = os.path.dirname(chrome_profile_path)
    try:
        if not os.path.exists(profile_dir):
            os.makedirs(profile_dir)
            logger.info(f"Created directory for Chrome profile: {profile_dir}")
        if not os.path.exists(chrome_profile_path):
            os.makedirs(chrome_profile_path)
            logger.info(f"Created Chrome profile directory: {chrome_profile_path}")
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
                    logger.info("Element is now visible after scrolling into view.")
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
                        logger.info("Maximum scroll attempts reached. Ending scroll.")
                        break

                if current_scroll_position >= end_position:
                    logger.debug("Reached the bottom of the element.")
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
    options.binary_location = '/usr/bin/google-chrome'  # Update as necessary
    
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
        logger.info(f"Using Chrome profile directory: {chrome_profile_path}")
    else:
        options.add_argument("--incognito")
        logger.info("Using Chrome in incognito mode")

    return options

def print_colored(text, color_code):
    reset = "\033[0m"
    logger.debug(f"Printing text in color {color_code}: {text}")
    print(f"{color_code}{text}{reset}")

def print_red(text):
    red = "\033[91m"
    print_colored(text, red)

def print_yellow(text):
    yellow = "\033[93m"
    print_colored(text, yellow)

def string_width(text, font, font_size):
    try:
        bbox = font.getbbox(text)
        width = bbox[2] - bbox[0]
        logger.debug(f"Calculated string width for '{text}': {width}")
        return width
    except Exception as e:
        logger.error(f"Error calculating string width: {e}", exc_info=True)
        return 0