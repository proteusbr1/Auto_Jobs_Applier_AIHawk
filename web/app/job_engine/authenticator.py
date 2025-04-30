"""
LinkedIn authentication module for the Auto_Jobs_Applier_AIHawk web application.
This module handles user authentication with LinkedIn.
"""
import os
import time
from pathlib import Path

from selenium.common.exceptions import (
    NoSuchElementException, 
    TimeoutException, 
    NoAlertPresentException, 
    UnexpectedAlertPresentException
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from flask import current_app
from loguru import logger

from app import db
from app.models import User


class LinkedInAuthenticator:
    """
    Handles LinkedIn authentication for a specific user.
    """

    def __init__(self, driver, user_id, session_manager=None):
        """
        Initialize the LinkedInAuthenticator.

        Args:
            driver: The Selenium WebDriver instance.
            user_id (int): The ID of the user to authenticate.
            session_manager: Optional session manager for managing browser sessions.
        """
        self.driver = driver
        self.user_id = user_id
        self.session_manager = session_manager
        self.user = User.query.get(user_id)
        
        if not self.user:
            logger.error(f"User with ID {user_id} not found")
            raise ValueError(f"User with ID {user_id} not found")
        
        # Get user-specific data directory
        self.user_data_dir = self._get_user_data_dir()
        
        logger.debug(f"LinkedInAuthenticator initialized for user {user_id}")

    def _get_user_data_dir(self):
        """
        Get the user-specific data directory.

        Returns:
            Path: The path to the user's data directory.
        """
        user_data_dir = current_app.config['USER_DATA_DIR']
        user_dir = Path(user_data_dir, str(self.user_id))
        firefox_profile_dir = user_dir / 'firefox_profile'
        
        # Create directories if they don't exist
        os.makedirs(firefox_profile_dir, exist_ok=True)
        
        return firefox_profile_dir

    def start(self):
        """
        Start the authentication process.
        """
        logger.debug(f"Starting browser to log in to LinkedIn for user {self.user_id}")
        
        if self.is_logged_in():
            logger.debug(f"User {self.user_id} is already logged in. Skipping login process.")
            return
        
        logger.debug(f"User {self.user_id} is not logged in. Proceeding with login.")
        self.handle_login()

    def handle_login(self):
        """
        Handle the login process.
        """
        logger.debug(f"Navigating to the LinkedIn login page for user {self.user_id}...")
        try:
            # Check if we have stored LinkedIn session cookies
            if self.user.linkedin_session:
                try:
                    # Try to restore the session from cookies
                    logger.debug(f"Attempting to restore LinkedIn session from cookies for user {self.user_id}")
                    self.driver.get("https://www.linkedin.com")
                    
                    # Add cookies to the driver
                    import json
                    cookies = json.loads(self.user.linkedin_session)
                    for cookie in cookies:
                        try:
                            self.driver.add_cookie(cookie)
                        except Exception as cookie_error:
                            logger.warning(f"Error adding cookie for user {self.user_id}: {cookie_error}")
                    
                    # Refresh the page to apply cookies
                    self.driver.refresh()
                    
                    # Check if we're logged in
                    if self.is_logged_in():
                        logger.debug(f"Successfully restored LinkedIn session for user {self.user_id}")
                        return
                    else:
                        logger.warning(f"Failed to restore LinkedIn session for user {self.user_id}. Proceeding with manual login.")
                except Exception as session_error:
                    logger.warning(f"Error restoring LinkedIn session for user {self.user_id}: {session_error}. Proceeding with manual login.")
            
            # If we don't have stored cookies or failed to restore the session, proceed with manual login
            self.driver.get("https://www.linkedin.com/login")
            if 'feed' in self.driver.current_url:
                logger.debug(f"User {self.user_id} is already logged in.")
                return
            
            # In the multi-user version, we wait for manual login
            # This could be enhanced with stored credentials in a secure way
            self.enter_credentials()
            self.handle_security_check()
            
            # Save the session cookies for future use
            self._save_session_cookies()
            
            # Update user's last LinkedIn login time
            self._update_linkedin_login_time()
            
        except Exception as e:
            logger.exception(f"An error occurred during handle_login for user {self.user_id}: {e}")
            raise

    def enter_credentials(self):
        """
        Wait for the user to enter credentials manually.
        """
        logger.debug(f"Waiting for user {self.user_id} to enter credentials...")
        check_interval = 4  # Interval to log the current URL

        try:
            while True:
                current_url = self.driver.current_url
                logger.debug(f"Please login on {current_url} for user {self.user_id}")

                if 'feed' in current_url:
                    logger.debug(f"Login successful for user {self.user_id}, redirected to feed page.")
                    break
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.ID, "password"))
                    )
                    logger.debug(f"Password field detected for user {self.user_id}, waiting for login completion.")
                except TimeoutException:
                    logger.warning(f"Password field not found yet for user {self.user_id}. Retrying...")

                time.sleep(check_interval)
        except TimeoutException:
            logger.error(f"Login form not found for user {self.user_id}. Aborting login.")
        except Exception as e:
            logger.exception(f"An unexpected error occurred in enter_credentials for user {self.user_id}: {e}")
            raise

    def handle_security_check(self):
        """
        Handle LinkedIn security checks.
        """
        logger.debug(f"Handling security check for user {self.user_id}...")
        try:
            WebDriverWait(self.driver, 10).until(
                EC.url_contains('https://www.linkedin.com/checkpoint/challengesV2/')
            )
            logger.warning(f"Security checkpoint detected for user {self.user_id}. Please complete the challenge.")
            WebDriverWait(self.driver, 300).until(
                EC.url_contains('https://www.linkedin.com/feed/')
            )
            logger.debug(f"Security check completed for user {self.user_id}.")
        except TimeoutException:
            logger.error(f"Security check not completed within the timeout period for user {self.user_id}. Please try again later.")
        except Exception as e:
            logger.exception(f"An unexpected error occurred during handle_security_check for user {self.user_id}: {e}")
            raise

    def is_logged_in(self):
        """
        Check if the user is logged in to LinkedIn.

        Returns:
            bool: True if the user is logged in, False otherwise.
        """
        logger.debug(f"Checking if user {self.user_id} is logged in...")
        try:
            self.driver.get('https://www.linkedin.com/feed')
            
            # Multiple ways to check if logged in
            
            # Method 1: Check for "Start a post" text in any button
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//button[contains(.,'Start a post')]"))
                )
                logger.debug(f"Found 'Start a post' button indicating user {self.user_id} is logged in.")
                return True
            except TimeoutException:
                logger.debug(f"Could not find 'Start a post' button for user {self.user_id}. Trying alternative methods.")
            
            # Method 2: Check for profile image
            try:
                profile_img_elements = self.driver.find_elements(By.XPATH, "//img[contains(@alt, 'Photo of') or contains(@alt, 'profile photo')]")
                if profile_img_elements:
                    logger.debug(f"Profile image found. Assuming user {self.user_id} is logged in.")
                    return True
            except Exception as e:
                logger.debug(f"Error checking for profile image for user {self.user_id}: {e}")
            
            # Method 3: Check for feed content
            try:
                feed_elements = self.driver.find_elements(By.CLASS_NAME, "feed-shared-update-v2")
                if feed_elements:
                    logger.debug(f"Feed content found. User {self.user_id} is logged in.")
                    return True
            except Exception as e:
                logger.debug(f"Error checking for feed content for user {self.user_id}: {e}")
            
            # Method 4: Check URL - if we're redirected to login page, we're not logged in
            if 'login' in self.driver.current_url or 'checkpoint' in self.driver.current_url:
                logger.debug(f"Redirected to login page. User {self.user_id} is not logged in.")
                return False
                
            logger.debug(f"Could not definitively determine login status for user {self.user_id}. Assuming not logged in.")
            return False

        except TimeoutException:
            logger.error(f"Page elements took too long to load or were not found for user {self.user_id}.")
            # Check if we're on the login page
            if 'login' in self.driver.current_url:
                logger.debug(f"On login page. User {self.user_id} is not logged in.")
                return False
            return False
        except Exception as e:
            logger.exception(f"An unexpected error occurred in is_logged_in for user {self.user_id}: {e}")
            return False

    def _save_session_cookies(self):
        """
        Save the LinkedIn session cookies to the user's record.
        """
        try:
            # Get cookies from the driver
            cookies = self.driver.get_cookies()
            if cookies:
                # Save cookies to the user's record
                import json
                self.user.linkedin_session = json.dumps(cookies)
                self.user.linkedin_authenticated = True
                db.session.commit()
                logger.debug(f"Saved LinkedIn session cookies for user {self.user_id}")
            else:
                logger.warning(f"No cookies found to save for user {self.user_id}")
        except Exception as e:
            logger.exception(f"Error saving LinkedIn session cookies for user {self.user_id}: {e}")
            db.session.rollback()

    def _update_linkedin_login_time(self):
        """
        Update the user's last LinkedIn login time in the database.
        """
        try:
            # This would be implemented to track when users last logged in to LinkedIn
            # Could be used for session management and analytics
            pass
        except Exception as e:
            logger.exception(f"Error updating LinkedIn login time for user {self.user_id}: {e}")
