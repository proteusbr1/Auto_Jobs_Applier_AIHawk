"""
LinkedIn authentication module for AIHawk.

This module handles the authentication process for LinkedIn, allowing AIHawk to
access LinkedIn on behalf of the user to search and apply for jobs.
"""
import os
import json
import time
import logging
from flask import current_app, session, redirect, url_for, render_template, flash, request
from flask_login import current_user, login_required
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from app import db
from app.models import User

# Configure logging
logger = logging.getLogger(__name__)

class LinkedInAuth:
    """Class to handle LinkedIn authentication."""
    
    def __init__(self, headless=False):
        """Initialize the LinkedIn authentication handler.
        
        Args:
            headless (bool): Whether to run the browser in headless mode.
        """
        self.headless = headless
        self.driver = None
        self.is_authenticated = False
    
    def setup_driver(self):
        """Set up the Chrome driver for LinkedIn authentication."""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        
        # Add additional options for stability
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Set user agent to avoid detection
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")
        
        # Create a new Chrome driver
        self.driver = webdriver.Chrome(options=chrome_options)
        
        # Set timeout for page loads
        self.driver.set_page_load_timeout(30)
        
        return self.driver
    
    def open_linkedin(self):
        """Open LinkedIn in the browser."""
        if not self.driver:
            self.setup_driver()
        
        try:
            # Navigate to LinkedIn
            self.driver.get("https://www.linkedin.com/")
            logger.info("Opened LinkedIn in browser")
            return True
        except Exception as e:
            logger.error(f"Error opening LinkedIn: {str(e)}")
            return False
    
    def check_if_logged_in(self):
        """Check if the user is already logged in to LinkedIn."""
        if not self.driver:
            return False
        
        try:
            # Check for elements that would indicate the user is logged in
            # This could be the presence of the feed or profile elements
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.ID, "global-nav"))
            )
            logger.info("User is already logged in to LinkedIn")
            self.is_authenticated = True
            return True
        except (TimeoutException, NoSuchElementException):
            logger.info("User is not logged in to LinkedIn")
            return False
    
    def wait_for_login(self, timeout=300):
        """Wait for the user to log in to LinkedIn.
        
        Args:
            timeout (int): Maximum time to wait for login in seconds.
            
        Returns:
            bool: True if login successful, False otherwise.
        """
        if not self.driver:
            return False
        
        try:
            # Wait for the global navigation element to appear, which indicates successful login
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.ID, "global-nav"))
            )
            logger.info("User successfully logged in to LinkedIn")
            self.is_authenticated = True
            return True
        except TimeoutException:
            logger.error("Timeout waiting for LinkedIn login")
            return False
    
    def close_driver(self):
        """Close the Chrome driver."""
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
                logger.info("Closed Chrome driver")
            except Exception as e:
                logger.error(f"Error closing Chrome driver: {str(e)}")
    
    def get_session_cookies(self):
        """Get the session cookies from the browser.
        
        Returns:
            list: List of cookie dictionaries.
        """
        if not self.driver:
            return []
        
        try:
            cookies = self.driver.get_cookies()
            logger.info(f"Retrieved {len(cookies)} cookies from LinkedIn session")
            return cookies
        except Exception as e:
            logger.error(f"Error getting session cookies: {str(e)}")
            return []
    
    def save_session_to_user(self, user_id):
        """Save the LinkedIn session to the user.
        
        Args:
            user_id (int): The ID of the user to save the session for.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        if not self.driver or not self.is_authenticated:
            return False
        
        try:
            # Get the session cookies
            cookies = self.get_session_cookies()
            if not cookies:
                return False
            
            # Save the cookies to the user
            user = User.query.get(user_id)
            if not user:
                logger.error(f"User with ID {user_id} not found")
                return False
            
            # Store the cookies as JSON in the user's linkedin_session field
            user.linkedin_session = json.dumps(cookies)
            user.linkedin_authenticated = True
            db.session.commit()
            
            logger.info(f"Saved LinkedIn session for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving LinkedIn session: {str(e)}")
            db.session.rollback()
            return False


def init_linkedin_auth_routes(app):
    """Initialize the LinkedIn authentication routes.
    
    Args:
        app (Flask): The Flask application.
    """
    from app.linkedin import linkedin_bp
    
    @linkedin_bp.route('/auth/start')
    @login_required
    def start_auth():
        """Start the LinkedIn authentication process."""
        # Check if the user is already authenticated with LinkedIn
        if current_user.linkedin_authenticated:
            flash("You are already authenticated with LinkedIn.", "info")
            return redirect(url_for('main.dashboard'))
        
        # Create a new LinkedIn authentication session
        session['linkedin_auth_started'] = True
        
        # Redirect to the LinkedIn auth page
        return redirect(url_for('linkedin.auth_process'))
    
    @linkedin_bp.route('/auth/process')
    @login_required
    def auth_process():
        """Process the LinkedIn authentication."""
        # Check if the auth process has been started
        if not session.get('linkedin_auth_started'):
            flash("LinkedIn authentication process not started.", "warning")
            return redirect(url_for('main.linkedin_auth'))
        
        # Create a new LinkedIn authentication handler
        auth_handler = LinkedInAuth(headless=False)
        
        try:
            # Open LinkedIn
            if not auth_handler.open_linkedin():
                flash("Failed to open LinkedIn. Please try again.", "danger")
                return redirect(url_for('main.linkedin_auth'))
            
            # Check if already logged in
            if auth_handler.check_if_logged_in():
                # Save the session
                if auth_handler.save_session_to_user(current_user.id):
                    flash("Successfully authenticated with LinkedIn.", "success")
                else:
                    flash("Failed to save LinkedIn session. Please try again.", "danger")
                
                # Close the driver
                auth_handler.close_driver()
                
                # Clear the session
                session.pop('linkedin_auth_started', None)
                
                return redirect(url_for('main.dashboard'))
            
            # Wait for the user to log in
            if auth_handler.wait_for_login():
                # Save the session
                if auth_handler.save_session_to_user(current_user.id):
                    flash("Successfully authenticated with LinkedIn.", "success")
                else:
                    flash("Failed to save LinkedIn session. Please try again.", "danger")
            else:
                flash("LinkedIn authentication timed out. Please try again.", "warning")
            
            # Close the driver
            auth_handler.close_driver()
            
            # Clear the session
            session.pop('linkedin_auth_started', None)
            
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            logger.error(f"Error during LinkedIn authentication: {str(e)}")
            flash("An error occurred during LinkedIn authentication. Please try again.", "danger")
            
            # Close the driver
            if auth_handler:
                auth_handler.close_driver()
            
            # Clear the session
            session.pop('linkedin_auth_started', None)
            
            return redirect(url_for('main.linkedin_auth'))
    
    @linkedin_bp.route('/auth/status')
    @login_required
    def auth_status():
        """Check the LinkedIn authentication status."""
        if current_user.linkedin_authenticated:
            return {"authenticated": True}
        else:
            return {"authenticated": False}
