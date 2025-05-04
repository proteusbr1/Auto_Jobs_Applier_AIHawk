# src/utils.py
"""
General utility functions for the web automation bot.

• Logging (Loguru + stdlib intercept)
• Persistent-profile Chrome setup with anti-detection tweaks
• Helpers: directory utils, screenshot, human-typing, smooth scroll, etc.

‼️ 2025-05-02 — FIXES
────────────────────
1. Always fall back to DEFAULT_CHROME_PROFILE_DIR when profile_path/env var absent
2. DEFAULT_CHROME_PROFILE_DIR is now absolute (~/.aihawk/…) to avoid duplicates
3. Example hook to persist the **same** User-Agent between runs (optional)
"""

from __future__ import annotations

import os
import random
import re
import sys
import time
import logging
import pickle
from pathlib import Path
from datetime import datetime
from typing import Optional, Union

# ── Third-party ──────────────────────────────────────────────────────────────
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

try:
    from fake_useragent import UserAgent
    _has_fake_useragent = True
except ImportError:
    logger.warning("`fake-useragent` not installed. Falling back to a default UA.  "
                   "pip install fake-useragent for better stealth.")
    _has_fake_useragent = False

# ── Defaults ────────────────────────────────────────────────────────────────
DEFAULT_LOG_DIR            = Path("./logs")
DEFAULT_LOG_FILENAME       = "automation_run.log"
DEFAULT_CONSOLE_LOG_LEVEL  = "INFO"
DEFAULT_FILE_LOG_LEVEL     = "DEBUG"
DEFAULT_SCREENSHOT_DIR     = Path("./screenshots")

# *Absolute* path  evita múltiplos perfis se rodar de diretórios diferentes
DEFAULT_CHROME_PROFILE_DIR = Path.home() / ".aihawk" / "chrome_profile" / "default_user"
DEFAULT_BROWSER_LANGUAGE   = "en-US,en;q=0.9"

ALLOWED_LOG_LEVELS = [
    "TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"
]

# ── Logging intercept helper ────────────────────────────────────────────────
class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            if frame.f_back:
                frame = frame.f_back
                depth += 1
            else:
                break
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

# ── Logging setup ───────────────────────────────────────────────────────────
def configure_logging() -> None:
    console_level = os.getenv("CONSOLE_LOG_LEVEL", DEFAULT_CONSOLE_LOG_LEVEL).upper()
    file_level    = os.getenv("FILE_LOG_LEVEL",    DEFAULT_FILE_LOG_LEVEL   ).upper()

    if console_level not in ALLOWED_LOG_LEVELS:
        print(f"[utils] invalid CONSOLE_LOG_LEVEL {console_level!r}, defaulting to INFO", file=sys.stderr)
        console_level = DEFAULT_CONSOLE_LOG_LEVEL
    if file_level not in ALLOWED_LOG_LEVELS:
        print(f"[utils] invalid FILE_LOG_LEVEL {file_level!r}, defaulting to DEBUG", file=sys.stderr)
        file_level = DEFAULT_FILE_LOG_LEVEL

    log_dir = DEFAULT_LOG_DIR
    log_path = log_dir / DEFAULT_LOG_FILENAME
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Error creating log dir {log_dir}: {e}", file=sys.stderr)
        file_level = "CRITICAL"

    logger.remove()
    logger.add(
        sys.stderr,
        level=console_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>",
        colorize=True,
        enqueue=True,
    )
    logger.add(
        log_path,
        level=file_level,
        rotation="100 MB",
        retention="14 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
               "{process} | {name}:{function}:{line} - {message}",
        enqueue=True,
    )
    logging.basicConfig(handlers=[InterceptHandler()], level=0)

# ── Directory helpers ───────────────────────────────────────────────────────
def ensure_directory(dir_path: Union[str, Path]) -> Optional[Path]:
    try:
        path = Path(dir_path)
        path.mkdir(parents=True, exist_ok=True)
        return path
    except Exception as e:
        logger.error(f"ensure_directory({dir_path}) failed: {e}")
        return None

# ── Chrome profile helpers ──────────────────────────────────────────────────
def ensure_chrome_profile(profile_dir: Path = DEFAULT_CHROME_PROFILE_DIR) -> Optional[Path]:
    logger.debug(f"Ensuring Chrome profile dir exists: {profile_dir}")
    return ensure_directory(profile_dir)

# optional: persist a UA between runs (prevents “device change” logouts)
_UA_FILE = DEFAULT_CHROME_PROFILE_DIR.parent / ".user_agent.txt"
def _get_persistent_ua() -> str:
    if _UA_FILE.exists():
        return _UA_FILE.read_text().strip()
    if _has_fake_useragent:
        try:
            ua = UserAgent().chrome
        except Exception:
            ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    else:
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    try:
        _UA_FILE.parent.mkdir(parents=True, exist_ok=True)
        _UA_FILE.write_text(ua)
    except OSError:
        pass
    return ua

# ── Chrome options builder ─────────────────────────────────────────────────
def chrome_browser_options(
    headless: bool = False,
    profile_path: Optional[Path] = None,
    binary_location: Optional[str] = None,
    proxy: Optional[str] = None,
) -> ChromeOptions:
    opts = ChromeOptions()

    # ── Resolve parameters/ENV ────────────────────────────────────────────
    env_headless = os.getenv("HEADLESS", str(headless)).lower() == "true"
    if not os.getenv("DISPLAY") and not env_headless:
        logger.info("DISPLAY not set – forcing headless mode")
        env_headless = True

    env_profile  = Path(os.getenv("CHROME_PROFILE_PATH")) if os.getenv("CHROME_PROFILE_PATH") else profile_path
    # 🔧 FIX – fallback obrigatório
    if env_profile is None:
        env_profile = DEFAULT_CHROME_PROFILE_DIR
    env_profile = Path(env_profile).expanduser().resolve()

    env_binary   = os.getenv("CHROME_BINARY_PATH") or binary_location
    env_lang     = os.getenv("BROWSER_LANG", DEFAULT_BROWSER_LANGUAGE)

    # ── Basic headless/headed flags ───────────────────────────────────────
    if env_headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1920,1080")
    else:
        opts.add_argument("--start-maximized")

    if env_binary and Path(env_binary).exists():
        opts.binary_location = str(env_binary)

    # ── Generic stability / stealth flags ─────────────────────────────────
    opts.page_load_strategy = "eager"
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--ignore-certificate-errors")
    opts.add_argument("--disable-background-timer-throttling")
    opts.add_argument("--disable-backgrounding-occluded-windows")
    opts.add_argument("--disable-popup-blocking")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    opts.add_experimental_option("useAutomationExtension", False)

    # User-Agent (persistent)
    ua = _get_persistent_ua()
    opts.add_argument(f"user-agent={ua}")

    # Language
    opts.add_argument(f"--lang={env_lang}")

    # Preferences
    prefs = {
        "profile.default_content_setting_values.images": 1,
        "profile.managed_default_content_settings.stylesheets": 1,
        "profile.default_content_setting_values.cookies": 1,
        "profile.default_content_setting_values.javascript": 1,
        "profile.default_content_setting_values.plugins": 2,
        "profile.default_content_setting_values.popups": 2,
        "profile.default_content_setting_values.geolocation": 2,
        "profile.default_content_setting_values.notifications": 2,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
    }
    opts.add_experimental_option("prefs", prefs)

    # Persistent profile flags
    if ensure_chrome_profile(env_profile):
        opts.add_argument(f"--user-data-dir={env_profile.parent}")
        opts.add_argument(f"--profile-directory={env_profile.name}")
        logger.info(f"Using Chrome profile → {env_profile}")
    else:
        logger.error("Profile directory could not be created; session will not persist.")

    if proxy:
        opts.add_argument(f"--proxy-server={proxy}")

    return opts

# ── Selenium helpers (scroll, type, screenshots) ───────────────────────────
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
    

def is_scrollable(driver: WebDriver, el: WebElement) -> bool:
    try:
        return driver.execute_script(
            "return arguments[0].scrollHeight > arguments[0].clientHeight;", el
        )
    except Exception:
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

def type_like_human(el: WebElement, text: str,
                    min_delay: float = 0.05, max_delay: float = 0.18) -> None:
    for ch in text:
        el.send_keys(ch)
        time.sleep(random.uniform(min_delay, max_delay))

# ── Cookie persistence helpers (plan B) ─────────────────────────────────────
COOKIE_FILE = DEFAULT_CHROME_PROFILE_DIR.parent / "cookies.pkl"

def save_cookies(driver: WebDriver) -> None:
    try:
        pickle.dump(driver.get_cookies(), COOKIE_FILE.open("wb"))
        logger.debug(f"Saved cookies → {COOKIE_FILE}")
    except Exception as e:
        logger.error(f"save_cookies failed: {e}")

def load_cookies(driver: WebDriver, url: str) -> None:
    if not COOKIE_FILE.exists():
        return
    driver.get(url)
    try:
        for c in pickle.load(COOKIE_FILE.open("rb")):
            driver.add_cookie(c)
        driver.refresh()
        logger.debug("Cookies re-loaded & page refreshed")
    except Exception as e:
        logger.error(f"load_cookies failed: {e}")
