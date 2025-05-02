# src/job_manager/job_extractor.py
"""
Extracts job information (title, company, location, link, etc.)
from web elements on a job listing page (specifically designed for LinkedIn).
Handles potential page load issues and uses multiple locator strategies,
adapted to recent HTML structure changes.
"""
import time
from loguru import logger
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup

# Selenium imports
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Utils (relative import)
try:
    from .. import utils
except ImportError:
    logger.error("Failed to import src.utils using relative path. Check structure.")
    utils = None

# Navigator needed for scrolling (relative import)
from .job_navigator import JobNavigator


class JobExtractor:
    """
    Extracts structured job information from Selenium WebElements representing job listings.
    Adapts to LinkedIn structure changes by using robust relative locators.
    """
    # --- Locators (Ensure all are tuples) ---
    NO_RESULTS_BANNER_LOCATOR = (By.CLASS_NAME, 'jobs-search-no-results-banner')
    JOB_TILE_WITH_ID_LOCATOR = (By.CSS_SELECTOR, 'li.scaffold-layout__list-item[data-occludable-job-id]')
    CONTAINER_LOCATOR_VIA_SENTINEL = (By.XPATH, "//div[@data-results-list-top-scroll-sentinel]/following-sibling::ul[1]")
    CONTAINER_LOCATOR_VIA_LI_PARENT = (By.XPATH, "//li[@data-occludable-job-id]/ancestor::ul[1]")
    CONTAINER_LOCATOR_OLD_XPATH = (By.XPATH, "//main[@id='main']//div[contains(@class, 'scaffold-layout__list-detail-inner')]//ul")
    CONTAINER_LOCATOR_FALLBACK_XPATH = (By.XPATH, "//main[@id='main']//ul")
    JOB_TILE_LOCATOR_PRIMARY = JOB_TILE_WITH_ID_LOCATOR
    JOB_TILE_LOCATOR_FALLBACK = (By.CSS_SELECTOR, 'li.scaffold-layout__list-item')
    TITLE_LINK_SELECTOR_PRIMARY = (By.CSS_SELECTOR, 'a.job-card-list__title, a.job-card-container__link')
    TITLE_LINK_SELECTOR_FALLBACK = (By.XPATH, './/a//strong')
    COMPANY_SELECTOR_PRIMARY = (By.CSS_SELECTOR, 'div.artdeco-entity-lockup__subtitle span:not([class])')
    COMPANY_SELECTOR_LINK = (By.CSS_SELECTOR, 'a.job-card-container__company-name, a.job-card-list__company-name')
    COMPANY_SELECTOR_SUBTITLE_DIV = (By.CSS_SELECTOR, 'div.artdeco-entity-lockup__subtitle')
    LOCATION_SELECTOR_PRIMARY = (By.CSS_SELECTOR, 'div.artdeco-entity-lockup__caption li span[dir="ltr"]')
    LOCATION_SELECTOR_SUBTITLE_DIV = COMPANY_SELECTOR_SUBTITLE_DIV
    LINK_SELECTOR_PRIMARY = (By.CSS_SELECTOR, "a[href*='/jobs/view/']")
    LINK_SELECTOR_TAG_FALLBACK = (By.TAG_NAME, "a")
    APPLY_METHOD_SELECTOR_XPATH = (By.XPATH, ".//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'easy apply')]")
    JOB_STATE_SELECTOR = (By.CSS_SELECTOR, 'li.job-card-container__footer-job-state')
    # --- End Locators ---

    DEFAULT_WAIT_TIME = 20

    def __init__(self, driver: WebDriver, wait_time: Optional[int] = None):
        """Initializes the JobExtractor."""
        if not isinstance(driver, WebDriver):
             raise TypeError("driver must be an instance of selenium.webdriver.remote.webdriver.WebDriver")
        self.driver = driver
        self.wait_time = wait_time if wait_time is not None else self.DEFAULT_WAIT_TIME
        self.wait = WebDriverWait(self.driver, self.wait_time)
        self.navigator = JobNavigator(driver, self.wait_time)
        logger.debug("JobExtractor initialized.")

    def _wait_for_page_load_stability(self, wait_time: int = 5) -> bool:
        """Waits for document readyState and a basic stable element."""
        logger.trace("Waiting for page load stability (document.readyState == 'complete')...")
        try:
            WebDriverWait(self.driver, wait_time).until(
                lambda driver: driver.execute_script('return document.readyState') == 'complete'
            )
            WebDriverWait(self.driver, wait_time).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            logger.trace("Page load stability confirmed.")
            return True
        except TimeoutException:
            logger.warning(f"Timed out waiting {wait_time}s for page readyState or body tag.")
            return False
        except WebDriverException as e:
             logger.error(f"WebDriverException while waiting for page stability: {e}")
             if "connection refused" in str(e).lower():
                  raise e
             return False

    def get_jobs_from_page(self) -> List[WebElement]:
        """Fetches all job tile WebElements from the current job search results page."""
        logger.debug("Attempting to fetch job elements from the current page...")
        if not self._wait_for_page_load_stability(wait_time=5):
             logger.warning("Initial page stability check failed. Extraction may be unreliable.")

        # 1. Initial Page Content Check
        try:
            logger.debug(f"Waiting up to {self.wait_time}s for initial page content...")
            self.wait.until(EC.any_of(
                EC.presence_of_element_located(self.NO_RESULTS_BANNER_LOCATOR),
                EC.presence_of_element_located(self.JOB_TILE_WITH_ID_LOCATOR)
            ))
            logger.debug("Initial page elements detected.")
        except TimeoutException:
            logger.warning("Timed out waiting for initial job tiles or 'no results' banner.")
            if utils:
                utils.capture_screenshot(self.driver, "get_jobs_initial_timeout")
            return []
        except WebDriverException as e:
             logger.error(f"WebDriverException during initial page check: {e}")
             if "connection refused" in str(e).lower():
                  logger.critical("Connection refused - Cannot communicate with browser driver. Aborting extraction.")
                  raise e
             logger.warning("Proceeding extraction attempt despite WebDriverException.")

        # 2. Check for "No Results" Banner
        try:
            if self.driver.find_elements(*self.NO_RESULTS_BANNER_LOCATOR):
                logger.info("Detected 'No Results' banner. No jobs to extract.")
                return []
        except WebDriverException as e:
             logger.warning(f"WebDriverException checking for 'No Results' banner: {e}. Assuming results exist.")

        # 3. Locate Job List Container
        job_list_container: Optional[WebElement] = None
        container_locators = [
            ("Sentinel Sibling", self.CONTAINER_LOCATOR_VIA_SENTINEL),
            ("LI Parent", self.CONTAINER_LOCATOR_VIA_LI_PARENT),
            ("Old XPath", self.CONTAINER_LOCATOR_OLD_XPATH),
            ("Main UL Fallback", self.CONTAINER_LOCATOR_FALLBACK_XPATH),
        ]
        logger.debug("Locating main job list container using multiple strategies...")
        for name, locator in container_locators:
            try:
                job_list_container = WebDriverWait(self.driver, 7).until(
                    EC.presence_of_element_located(locator)
                )
                logger.debug(f"Job list container found using strategy '{name}': {locator}")
                break
            except TimeoutException:
                logger.trace(f"Job list container not found with strategy '{name}': {locator}")
                continue
            except WebDriverException as e:
                 logger.warning(f"WebDriverException checking container locator {locator} ('{name}'): {e}. Trying next.")
                 if "connection refused" in str(e).lower():
                     raise e
                 continue

        if not job_list_container:
            logger.error("Could not find the main job list container element after trying all strategies.")
            if utils:
                utils.capture_screenshot(self.driver, "job_container_not_found")
            return []

        # 4. Scroll Page
        logger.debug("Scrolling page to ensure all job tiles are loaded...")
        try:
            scroll_successful = self.navigator.scroll_jobs()
            if not scroll_successful:
                 logger.warning("Scrolling may not have completed successfully. Job list might be incomplete.")
        except WebDriverException as e:
             logger.error(f"WebDriverException during scrolling: {e}. Proceeding without full scroll.")
             if "connection refused" in str(e).lower():
                 raise e
        except Exception as e:
             logger.error(f"Unexpected error during scrolling: {e}. Proceeding without scroll.")

        # 5. Extract Job Tiles
        job_list_elements: List[WebElement] = []
        tile_locators = [
             ("Primary Tile Locator", self.JOB_TILE_LOCATOR_PRIMARY),
             ("Fallback Tile Locator", self.JOB_TILE_LOCATOR_FALLBACK)
        ]
        logger.debug("Extracting job tiles from container using updated strategies...")
        for name, locator in tile_locators:
             try:
                  job_list_elements = job_list_container.find_elements(*locator)
                  if job_list_elements:
                       logger.debug(f"Found {len(job_list_elements)} potential job tiles using locator '{name}': {locator}")
                       return job_list_elements
             except StaleElementReferenceException:
                  logger.warning(f"Stale element reference finding tiles with {locator} ('{name}'). Re-finding container...")
                  try:
                       # Re-find container using the most likely strategy again
                       job_list_container_retry = self.driver.find_element(*self.CONTAINER_LOCATOR_VIA_SENTINEL)
                       job_list_elements_retry = job_list_container_retry.find_elements(*locator)
                       if job_list_elements_retry:
                            logger.info(f"Re-fetched {len(job_list_elements_retry)} tiles after stale error using {locator} ('{name}').")
                            return job_list_elements_retry
                       else:
                            logger.warning("Found container but no tiles on retry.")
                  except Exception as retry_e:
                       logger.error(f"Failed attempt to re-fetch container/elements after stale error: {retry_e}")
                  # Continue to try next *tile* locator even if retry failed
             except WebDriverException as e:
                  logger.error(f"WebDriverException finding tiles with locator {locator} ('{name}'): {e}.")
                  if "connection refused" in str(e).lower():
                      raise e
             except Exception as e:
                  logger.warning(f"Error finding job tiles with locator {locator} ('{name}'): {e}")

        logger.error("Could not find any job tile elements using available locators after scrolling.")
        if utils:
            utils.capture_screenshot(self.driver, "no_job_tiles_found")
        return []

    # REMOVED _is_job_tile_loaded method

    def extract_job_information_from_tile(self, job_tile: WebElement) -> Optional[Tuple[str, str, str, str, Optional[str], Optional[str]]]:
        """
        Extracts structured job information from a single job tile WebElement
        using BeautifulSoup for faster parsing after getting the innerHTML.
        Returns None if essential information (title, link) cannot be extracted.
        """
        job_id = "unknown"
        html_content = ""
        try:
            # 1. Get Job ID (for logging and fallback link)
            job_id = job_tile.get_attribute('data-occludable-job-id') or "unknown"

            # 2. Get the HTML content ONCE
            html_content = job_tile.get_attribute('innerHTML')
            if not html_content:
                logger.warning(f"Job tile (ID: {job_id}) has no innerHTML content. Skipping.")
                return None

            # 3. Parse with BeautifulSoup
            # Using 'lxml' is generally faster if installed
            soup = BeautifulSoup(html_content, 'lxml')

            # 4. Extract data using BeautifulSoup selectors (adjust selectors as needed based on current LinkedIn HTML)

            # --- Title ---
            # First try to get title from aria-hidden element (visible text)
            title_element = soup.select_one('a.job-card-list__title span[aria-hidden="true"], a.job-card-container__link span[aria-hidden="true"]')
            if not title_element:
                # Fallback to more general selectors
                title_element = soup.select_one('a.job-card-list__title, a.job-card-container__link, a strong')
            
            job_title = title_element.get_text(strip=True) if title_element else ""
            
            # Fix duplicate title issue (e.g., "SalespersonSalesperson" -> "Salesperson")
            # Check if the title appears to be duplicated
            if job_title and len(job_title) >= 2:
                half_len = len(job_title) // 2
                first_half = job_title[:half_len]
                second_half = job_title[half_len:]
                
                # If both halves are identical or very similar, use just one half
                if first_half == second_half:
                    job_title = first_half
                # For cases where one half might have extra characters
                elif first_half.strip() == second_half.strip():
                    job_title = first_half.strip()
                # Check if the second half is a duplicate regardless of position
                elif job_title.endswith(job_title[:half_len]):
                    job_title = job_title[:half_len]

            # --- Link ---
            BASE_URL = "https://www.linkedin.com"
            link_element = soup.select_one("a[href*='/jobs/view/']")
            link = ""
            if link_element:
                href = link_element.get('href', '')
                if href:
                    if href.startswith('/'):
                        link = BASE_URL + href 
                    elif href.startswith('http'):
                        link = href 
                    # else: pular href com formato inválido

            # Fallback usando Job ID se o link não foi extraído do href
            if not link and job_id != "unknown":
                link = f"{BASE_URL}/jobs/view/{job_id}/" # Já inclui a base
                logger.trace(f"Link construído a partir do job ID (ID: {job_id})")

            # Limpar parâmetros do link final
            if link:
                link = link.split('?')[0]

            # --- Verificação Essencial ---
            if not job_title or not link:
                logger.warning(f"Informação essencial faltando (Title:'{job_title}', Link:'{link}') para o job tile (ID: {job_id}). Pulando.")
                return None


            # --- Essential Info Check ---
            if not job_title or not link:
                logger.warning(f"Missing essential info (Title:'{job_title}', Link:'{link}') for job tile (ID: {job_id}). Skipping.")
                # Optionally log soup object or html_content for debugging
                # logger.debug(f"Problematic HTML (ID: {job_id}): {html_content[:500]}")
                return None

            # --- Company ---
            # Try different selectors in order of preference
            company_element = soup.select_one('a.job-card-container__company-name, a.job-card-list__company-name') # Specific link
            if not company_element:
                # Try the subtitle approach (more complex)
                subtitle_div = soup.select_one('div.artdeco-entity-lockup__subtitle')
                if subtitle_div:
                    # Get text directly, split later if needed (avoids specific span selector)
                    company_text_raw = subtitle_div.get_text(separator=' ', strip=True)
                    # Basic split logic, might need refinement depending on format
                    if '·' in company_text_raw:
                        company = company_text_raw.split('·')[0].strip()
                    else:
                        company = company_text_raw # Assume it's just the company
                else:
                    company = "" # Fallback
            else:
                company = company_element.get_text(strip=True)


            # --- Location ---
            location_element = soup.select_one('div.artdeco-entity-lockup__caption li span[dir="ltr"]') # Specific location span
            if not location_element:
                # Fallback using subtitle split (reuse logic from company if applicable)
                subtitle_div = soup.select_one('div.artdeco-entity-lockup__subtitle')
                if subtitle_div:
                    location_text_raw = subtitle_div.get_text(separator=' ', strip=True)
                    if '·' in location_text_raw:
                        try:
                            job_location = location_text_raw.split('·')[1].strip()
                        except IndexError:
                            job_location = "" # Handle case where split fails
                    else:
                        job_location = "" # Subtitle didn't contain location separator
                else:
                    job_location = ""
            else:
                job_location = location_element.get_text(strip=True)

            # --- Apply Method ---
            # Search for text within the HTML snippet. Case-insensitive.
            apply_method = None
            if 'easy apply' in html_content.lower():
                apply_method = 'Easy Apply'

            # --- Job State ---
            state_element = soup.select_one(
                'li.job-card-container__footer-job-state'
            )
            job_state = (state_element.get_text(strip=True)
                        if state_element else None)


            # --- Logging & Return ---
            # Reduce log level for successful extractions to DEBUG or TRACE if INFO is too verbose
            logger.trace(f"Successfully extracted (BS): Title='{job_title}', Company='{company}', Location='{job_location}', Link='{link}', Apply='{apply_method}', State='{job_state}'")
            return job_title, company, job_location, link, apply_method, job_state

        except StaleElementReferenceException:
            # This *shouldn't* happen often if we get innerHTML quickly, but handle just in case
            logger.warning(f"Stale element encountered grabbing innerHTML for job tile (ID: {job_id}). Skipping.")
            return None
        except Exception as e:
            logger.error(f"Failed to extract job info using BeautifulSoup for tile (ID: {job_id}): {e}", exc_info=False) # Set exc_info=False to reduce noise unless debugging
            logger.debug(f"Problematic HTML snippet (ID: {job_id}): {html_content[:500]}") # Log snippet on error
            return None
