# src/job.py
"""
Defines the Job data structure and the JobCache class for tracking processed jobs.
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Optional, Set, Dict, List, Union, Final, Tuple # Added Tuple
from loguru import logger
from pathlib import Path
from datetime import datetime
import enum # For status types

# --- Job Status Enum ---
class JobStatus(enum.Enum):
    SUCCESS = "success"
    SEEN = "seen"
    SKIPPED_LOW_SCORE = "skipped_low_score"
    SKIPPED_LOW_SALARY = "skipped_low_salary"
    SKIPPED_BLACKLIST = "skipped_blacklist"
    FAILED_APPLICATION = "failed_application"
    JOB_SCORE = "job_score"

# --- Job Dataclass ---
@dataclass
class Job:
    """
    Represents a job posting with its relevant details.
    Uses default values for optional fields.
    """
    title: str
    company: str
    location: str
    link: str
    apply_method: Optional[str] = None
    state: Optional[str] = None
    salary: str = ""
    description: Optional[str] = None # <-- Make Optional
    pdf_path: Optional[Path] = None
    cover_letter_path: Optional[Path] = None
    recruiter_link: Optional[str] = None
    search_term: Optional[str] = None
    search_country: Optional[str] = None
    score: Optional[float] = None
    gpt_salary: Optional[float] = None

    def to_dict(self, exclude_fields: Optional[Set[str]] = None) -> Dict:
         """Converts dataclass to dictionary, optionally excluding fields."""
         if exclude_fields is None: exclude_fields = set()
         exclude_fields.add("description") # Exclude description by default
         data = asdict(self)
         if self.pdf_path: data['pdf_path'] = self.pdf_path.resolve().as_uri()
         else: data['pdf_path'] = None # Ensure None if path is None
         if self.cover_letter_path: data['cover_letter_path'] = self.cover_letter_path.resolve().as_uri()
         else: data['cover_letter_path'] = None # Ensure None if path is None
         return {k: v for k, v in data.items() if k not in exclude_fields}

# --- Job Cache Class ---
class JobCache:
    """
    Manages caches of processed job links loaded from and persisted to JSON files.
    """
    _CACHE_CONFIG: Final[Dict[JobStatus, Tuple[str, str]]] = {
        JobStatus.SUCCESS: ('_success_cache', 'success.json'),
        JobStatus.SEEN: ('_seen_cache', 'seen.json'), # Use 'seen.json'
        JobStatus.SKIPPED_LOW_SCORE: ('_skipped_low_score_cache', 'skipped_low_score.json'),
        JobStatus.SKIPPED_LOW_SALARY: ('_skipped_low_salary_cache', 'skipped_low_salary.json'),
        JobStatus.JOB_SCORE: ('_job_score_cache', 'job_score.json'),
        JobStatus.SKIPPED_BLACKLIST: ('_skipped_blacklist_cache', 'skipped_blacklist.json'), # Added
        JobStatus.FAILED_APPLICATION: ('_failed_application_cache', 'failed_application.json'), # Added
    }

    def __init__(self, output_directory: Path):
        """Initializes the JobCache."""
        logger.debug("Initializing JobCache...")
        if not isinstance(output_directory, Path): raise TypeError("output_directory must be a Path object.")
        self.output_directory: Path = output_directory
        try: self.output_directory.mkdir(parents=True, exist_ok=True)
        except OSError as e: logger.error(f"Failed to create cache directory {self.output_directory}: {e}", exc_info=True); raise RuntimeError(...) from e
        # Initialize all cache sets
        for status, (attr_name, _) in self._CACHE_CONFIG.items(): setattr(self, attr_name, set())
        self._load_all_caches()
        logger.info(f"JobCache initialized. Output directory: {self.output_directory}")
        for status, (attr_name, _) in self._CACHE_CONFIG.items(): logger.debug(f" - {status.name}: {len(getattr(self, attr_name))} links loaded.")

    def _load_cache_from_json(self, file_name: str) -> Set[str]:
        """Loads job links from a single JSON file into a set."""
        file_path = self.output_directory / file_name; link_set: Set[str] = set()
        if not file_path.exists(): logger.debug(f"Cache file not found: {file_name}"); return link_set
        try:
            with file_path.open('r', encoding='utf-8') as f:
                try: content = f.read().strip(); jobs_data = json.loads(content) if content else []
                except json.JSONDecodeError: logger.warning(f"Cache file '{file_name}' corrupted/empty."); return link_set
                if isinstance(jobs_data, list):
                    count = 0
                    for job in jobs_data:
                         if isinstance(job, dict) and 'link' in job and isinstance(job['link'], str): link_set.add(job['link']); count += 1
                         else: logger.warning(f"Invalid job entry format in {file_name}: {str(job)[:100]}")
                    logger.debug(f"Loaded {count} links from {file_name}")
                else: logger.warning(f"Unexpected format in {file_name}. Expected list, found {type(jobs_data)}.")
        except IOError as e: logger.error(f"IOError reading cache file {file_name}: {e}", exc_info=True)
        except Exception as e: logger.error(f"Unexpected error reading cache file {file_name}: {e}", exc_info=True)
        return link_set

    def _load_all_caches(self):
        """Loads all configured cache files into their respective in-memory sets."""
        logger.debug("Loading all cache JSON files...")
        for status, (attr_name, file_name) in self._CACHE_CONFIG.items():
            link_set = self._load_cache_from_json(file_name)
            setattr(self, attr_name, link_set) # Assign loaded set to correct attribute

    def _append_job_to_json(self, job_data: Dict, file_name: str):
        """Appends a job data dictionary to the specified JSON file (list format)."""
        file_path = self.output_directory / file_name
        logger.trace(f"Appending job data to {file_path}")
        try:
            existing_data = []
            if file_path.exists():
                try:
                    with file_path.open('r+', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content: existing_data = json.loads(content)
                        if not isinstance(existing_data, list): logger.error(f"Corrupted JSON {file_path}. Overwriting."); existing_data = []
                        existing_data.append(job_data)
                        f.seek(0)
                        json.dump(existing_data, f, indent=4, ensure_ascii=False)
                        f.truncate()
                except json.JSONDecodeError: logger.error(f"JSON decode error reading {file_path}. Overwriting."); existing_data = [job_data] # Start new list
                except IOError as e: logger.error(f"IOError appending {file_name}: {e}", exc_info=True); return # Don't proceed if IO fails
                except Exception as e: logger.error(f"Error appending {file_name}: {e}", exc_info=True); return
            # Write new file or overwrite corrupted one
            if not file_path.exists() or not isinstance(existing_data, list):
                with file_path.open('w', encoding='utf-8') as f: json.dump([job_data], f, indent=4, ensure_ascii=False)
                logger.debug(f"Created/Overwrote cache file: {file_name}")
        except Exception as e: logger.error(f"Failed critical write to {file_name}: {e}", exc_info=True)

    def record_job_status(self, job: Job, status: JobStatus):
        """Records the status of a job in memory and appends to the relevant JSON file."""
        if not isinstance(status, JobStatus):
             try: status = JobStatus(status)
             except ValueError: logger.error(f"Invalid status: {status}."); return
        if not job or not job.link: logger.error("Invalid job/link for recording status."); return
        logger.debug(f"Recording status '{status.name}' for job: {job.link}")
        if status in self._CACHE_CONFIG:
            attr_name, file_name = self._CACHE_CONFIG[status]
            cache_set = getattr(self, attr_name, None)
            if cache_set is None: logger.error(f"Internal cache error: Attr '{attr_name}' not found."); return
            if job.link not in cache_set: cache_set.add(job.link); logger.trace(f"Link added to in-memory cache: {attr_name}")
            else: logger.trace(f"Link already in in-memory cache: {attr_name}")
            job_dict = job.to_dict(exclude_fields={"description"}) # Use helper
            job_dict["status_recorded_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._append_job_to_json(job_dict, file_name)
        else: logger.error(f"Unknown status type '{status}' not configured.")

    # --- Status Checking Methods (THESE ARE THE METHODS TO CALL) ---
    def has_been_scored(self, link: str) -> bool: return link in self._job_score_cache
    def is_skipped_low_salary(self, link: str) -> bool: return link in self._skipped_low_salary_cache
    def is_skipped_low_score(self, link: str) -> bool: return link in self._skipped_low_score_cache
    def is_applied_successfully(self, link: str) -> bool: return link in self._success_cache
    def has_been_seen(self, link: str) -> bool: return link in self._seen_cache
    def is_skipped_blacklist(self, link: str) -> bool: return link in self._skipped_blacklist_cache # Added check
    def has_failed_application(self, link: str) -> bool: return link in self._failed_application_cache # Added check