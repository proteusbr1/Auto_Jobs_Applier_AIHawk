import random
import time

from selenium.common.exceptions import (
    NoSuchElementException, 
    TimeoutException, 
    NoAlertPresentException, 
    UnexpectedAlertPresentException
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from loguru import logger


class AIHawkAuthenticator:

    def __init__(self, driver=None):
        self.driver = driver
        logger.debug(f"AIHawkAuthenticator initialized with driver: {driver}")

    def start(self):
        logger.debug("Starting Chrome browser to log in to AIHawk.")
        if self.is_logged_in():
            logger.debug("User is already logged in. Skipping login process.")
            return
        logger.debug("User is not logged in. Proceeding with login.")
        self.handle_login()

    def handle_login(self):
        logger.debug("Navigating to the AIHawk login page...")
        try:
            self.driver.get("https://www.linkedin.com/login")
            if 'feed' in self.driver.current_url:
                logger.debug("User is already logged in.")
                return
            self.enter_credentials()
            self.handle_security_check()
        except Exception as e:
            logger.exception(f"An error occurred during handle_login: {e}")
            raise

    def enter_credentials(self):
        logger.debug("Entering credentials...")
        check_interval = 4  # Interval to log the current URL

        try:
            while True:
                current_url = self.driver.current_url
                logger.debug(f"Please login on {current_url}")

                if 'feed' in current_url:
                    logger.debug("Login successful, redirected to feed page.")
                    break
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.ID, "password"))
                    )
                    logger.debug("Password field detected, waiting for login completion.")
                except TimeoutException:
                    logger.warning("Password field not found yet. Retrying...")

                time.sleep(check_interval)
        except TimeoutException:
            logger.error("Login form not found. Aborting login.")
        except Exception as e:
            logger.exception(f"An unexpected error occurred in enter_credentials: {e}")
            raise

    def handle_security_check(self):
        logger.debug("Handling security check...")
        try:
            WebDriverWait(self.driver, 10).until(
                EC.url_contains('https://www.linkedin.com/checkpoint/challengesV2/')
            )
            logger.warning("Security checkpoint detected. Please complete the challenge.")
            WebDriverWait(self.driver, 300).until(
                EC.url_contains('https://www.linkedin.com/feed/')
            )
            logger.debug("Security check completed.")
        except TimeoutException:
            logger.error("Security check not completed within the timeout period. Please try again later.")
        except Exception as e:
            logger.exception(f"An unexpected error occurred during handle_security_check: {e}")
            raise

    def is_logged_in(self):
        logger.debug("Checking if user is logged in...")
        try:
            self.driver.get('https://www.linkedin.com/feed')
            WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'share-box-feed-entry__trigger'))
            )

            buttons = self.driver.find_elements(By.CLASS_NAME, 'share-box-feed-entry__trigger')
            logger.debug(f"Found {len(buttons)} 'Start a post' buttons.")

            for i, button in enumerate(buttons, start=1):
                logger.debug(f"Button {i} text: '{button.text.strip()}'")

            if any(button.text.strip().lower() == 'start a post' for button in buttons):
                logger.debug("Found 'Start a post' button indicating user is logged in.")
                return True

            profile_img_elements = self.driver.find_elements(By.XPATH, "//img[contains(@alt, 'Photo of')]")
            if profile_img_elements:
                logger.debug("Profile image found. Assuming user is logged in.")
                return True

            logger.debug("Did not find 'Start a post' button or profile image. User might not be logged in.")
            return False

        except TimeoutException:
            logger.error("Page elements took too long to load or were not found.")
            return False
        except Exception as e:
            logger.exception(f"An unexpected error occurred in is_logged_in: {e}")
            return False