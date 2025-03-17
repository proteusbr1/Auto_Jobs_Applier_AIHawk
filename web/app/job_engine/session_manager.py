"""
Browser session manager for the Auto_Jobs_Applier_AIHawk web application.
This module handles the creation and management of browser sessions for multiple users.
"""
import os
import time
import threading
import queue
from pathlib import Path
from typing import Dict, Optional, List

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from flask import current_app
from loguru import logger

from app import db
from app.models import User, Subscription


class BrowserSession:
    """
    Represents a browser session for a specific user.
    """
    
    def __init__(self, user_id: int, driver: webdriver.Chrome, created_at: float):
        """
        Initialize a browser session.
        
        Args:
            user_id (int): The ID of the user who owns this session.
            driver (webdriver.Chrome): The Selenium WebDriver instance.
            created_at (float): The timestamp when the session was created.
        """
        self.user_id = user_id
        self.driver = driver
        self.created_at = created_at
        self.last_used = created_at
        self.is_active = True
        self.lock = threading.RLock()
        
        logger.debug(f"Browser session created for user {user_id}")
    
    def acquire(self) -> bool:
        """
        Acquire the session lock.
        
        Returns:
            bool: True if the lock was acquired, False otherwise.
        """
        acquired = self.lock.acquire(blocking=False)
        if acquired:
            self.last_used = time.time()
        return acquired
    
    def release(self):
        """
        Release the session lock.
        """
        self.lock.release()
    
    def close(self):
        """
        Close the browser session.
        """
        try:
            self.driver.quit()
            self.is_active = False
            logger.debug(f"Browser session closed for user {self.user_id}")
        except Exception as e:
            logger.exception(f"Error closing browser session for user {self.user_id}: {e}")


class SessionManager:
    """
    Manages browser sessions for multiple users.
    """
    
    def __init__(self, max_sessions: int = 10, session_timeout: int = 3600):
        """
        Initialize the session manager.
        
        Args:
            max_sessions (int): Maximum number of concurrent sessions.
            session_timeout (int): Session timeout in seconds.
        """
        self.sessions: Dict[int, BrowserSession] = {}
        self.max_sessions = max_sessions
        self.session_timeout = session_timeout
        self.lock = threading.RLock()
        self.cleanup_thread = threading.Thread(target=self._cleanup_sessions, daemon=True)
        self.cleanup_thread.start()
        
        logger.debug(f"Session manager initialized with max_sessions={max_sessions}, session_timeout={session_timeout}")
    
    def get_session(self, user_id: int) -> Optional[webdriver.Chrome]:
        """
        Get a browser session for a user.
        
        Args:
            user_id (int): The ID of the user.
            
        Returns:
            Optional[webdriver.Chrome]: The WebDriver instance, or None if no session could be created.
        """
        with self.lock:
            # Check if user has an existing session
            if user_id in self.sessions and self.sessions[user_id].is_active:
                session = self.sessions[user_id]
                if session.acquire():
                    logger.debug(f"Reusing existing browser session for user {user_id}")
                    return session.driver
                else:
                    logger.warning(f"Session for user {user_id} is locked. Creating a new session.")
            
            # Check if user is allowed to create a new session
            if not self._can_create_session(user_id):
                logger.warning(f"User {user_id} is not allowed to create a new session")
                return None
            
            # Create a new session
            driver = self._create_browser_session(user_id)
            if driver:
                session = BrowserSession(user_id, driver, time.time())
                session.acquire()
                self.sessions[user_id] = session
                logger.debug(f"Created new browser session for user {user_id}")
                return driver
            
            logger.error(f"Failed to create browser session for user {user_id}")
            return None
    
    def release_session(self, user_id: int):
        """
        Release a browser session.
        
        Args:
            user_id (int): The ID of the user.
        """
        with self.lock:
            if user_id in self.sessions and self.sessions[user_id].is_active:
                self.sessions[user_id].release()
                logger.debug(f"Released browser session for user {user_id}")
    
    def close_session(self, user_id: int):
        """
        Close a browser session.
        
        Args:
            user_id (int): The ID of the user.
        """
        with self.lock:
            if user_id in self.sessions and self.sessions[user_id].is_active:
                self.sessions[user_id].close()
                del self.sessions[user_id]
                logger.debug(f"Closed browser session for user {user_id}")
    
    def _can_create_session(self, user_id: int) -> bool:
        """
        Check if a user is allowed to create a new session.
        
        Args:
            user_id (int): The ID of the user.
            
        Returns:
            bool: True if the user is allowed to create a new session, False otherwise.
        """
        # Check if we've reached the maximum number of sessions
        if len(self.sessions) >= self.max_sessions:
            logger.warning(f"Maximum number of sessions ({self.max_sessions}) reached")
            return False
        
        # Check if the user has an active subscription
        user = User.query.get(user_id)
        if not user:
            logger.error(f"User {user_id} not found")
            return False
        
        subscription = user.subscription
        if not subscription or not subscription.is_active():
            logger.warning(f"User {user_id} does not have an active subscription")
            return False
        
        # Check if the user has reached their maximum number of concurrent sessions
        max_concurrent_sessions = subscription.plan.max_concurrent_sessions if subscription.plan else 1
        user_sessions = sum(1 for session in self.sessions.values() if session.user_id == user_id and session.is_active)
        if user_sessions >= max_concurrent_sessions:
            logger.warning(f"User {user_id} has reached their maximum number of concurrent sessions ({max_concurrent_sessions})")
            return False
        
        return True
    
    def _create_browser_session(self, user_id: int) -> Optional[webdriver.Chrome]:
        """
        Create a new browser session.
        
        Args:
            user_id (int): The ID of the user.
            
        Returns:
            Optional[webdriver.Chrome]: The WebDriver instance, or None if the session could not be created.
        """
        try:
            # Get user-specific data directory
            user_data_dir = self._get_user_data_dir(user_id)
            
            # Set up Chrome options
            options = Options()
            options.add_argument(f"--user-data-dir={user_data_dir}")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-notifications")
            options.add_argument("--disable-infobars")
            options.add_argument("--mute-audio")
            
            # Create Chrome service
            service = ChromeService(ChromeDriverManager().install())
            
            # Create Chrome driver
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_window_size(1920, 1080)
            
            return driver
        except Exception as e:
            logger.exception(f"Error creating browser session for user {user_id}: {e}")
            return None
    
    def _get_user_data_dir(self, user_id: int) -> Path:
        """
        Get the user-specific data directory.
        
        Args:
            user_id (int): The ID of the user.
            
        Returns:
            Path: The path to the user's data directory.
        """
        user_data_dir = current_app.config['USER_DATA_DIR']
        user_dir = Path(user_data_dir, str(user_id))
        chrome_profile_dir = user_dir / 'chrome_profile'
        
        # Create directories if they don't exist
        os.makedirs(chrome_profile_dir, exist_ok=True)
        
        return chrome_profile_dir
    
    def _cleanup_sessions(self):
        """
        Periodically clean up inactive sessions.
        """
        while True:
            try:
                time.sleep(60)  # Check every minute
                
                with self.lock:
                    current_time = time.time()
                    sessions_to_close = []
                    
                    for user_id, session in self.sessions.items():
                        # Close sessions that have been inactive for too long
                        if session.is_active and current_time - session.last_used > self.session_timeout:
                            sessions_to_close.append(user_id)
                    
                    for user_id in sessions_to_close:
                        logger.debug(f"Closing inactive session for user {user_id}")
                        self.close_session(user_id)
            
            except Exception as e:
                logger.exception(f"Error in session cleanup: {e}")
