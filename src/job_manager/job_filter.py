# src/job_manager/job_filter.py
"""
Module for filtering Job objects based on defined criteria like blacklists and cache status.
"""
from loguru import logger
from typing import List, Optional, Set

# Ensure correct relative import if job.py is in parent dir
try:
    from ..job import Job, JobCache, JobStatus # Import JobStatus
except ImportError:
    from src.job import Job, JobCache, JobStatus


class JobFilter:
    """
    Filters Job objects based on title, company, description blacklists,
    and information stored in a JobCache.
    """
    INVALID_STATES = {"applied", "continue", "apply"}
    def __init__(self,
                 title_blacklist: Optional[List[str]] = None,
                 company_blacklist: Optional[List[str]] = None,
                 description_blacklist: Optional[List[str]] = None,
                 cache: Optional[JobCache] = None):
        """Initializes the JobFilter."""
        logger.debug("Initializing JobFilter...")
        self.title_blacklist: List[str] = title_blacklist or []
        self.company_blacklist: List[str] = company_blacklist or []
        self.description_blacklist: List[str] = description_blacklist or []
        if cache and not isinstance(cache, JobCache): raise TypeError("cache must be JobCache or None")
        self.cache: Optional[JobCache] = cache
        self.title_blacklist_set: Set[str] = {word.lower().strip() for word in self.title_blacklist if word}
        self.company_blacklist_set: Set[str] = {name.lower().strip() for name in self.company_blacklist if name}
        self.description_blacklist_lower: List[str] = [crit.lower().strip() for crit in self.description_blacklist if crit]
        logger.debug(f"JobFilter initialized successfully. Cache {'enabled' if cache else 'disabled'}.")

    def must_be_skipped(self, job: Job) -> bool:
        """Determines if a given job should be skipped based on various criteria."""
        if not isinstance(job, Job) or not job.link: logger.warning("Invalid Job passed to must_be_skipped."); return True
        link = job.link
        logger.debug(f"Filtering job: '{job.title}' at '{job.company}' ({link})")

        # --- Cache Checks (Using EXACT method names from refactored JobCache) ---
        if self.cache:
            # Use has_been_seen (renamed from is_in_is_seen)
            if self.cache.has_been_seen(link):
                logger.debug(f"Skipping: Job link already seen [{link}]")
                return True
            # Use is_skipped_low_salary
            if self.cache.is_skipped_low_salary(link):
                logger.debug(f"Skipping: Job previously skipped for low salary [{link}]")
                self.cache.record_job_status(job, JobStatus.SEEN) # Ensure marked as seen if re-encountered
                return True
            # Use is_skipped_low_score
            if self.cache.is_skipped_low_score(link):
                logger.debug(f"Skipping: Job previously skipped for low score/description [{link}]")
                self.cache.record_job_status(job, JobStatus.SEEN)
                return True
            # Use is_applied_successfully
            if self.cache.is_applied_successfully(link):
                logger.debug(f"Skipping: Job already applied successfully [{link}]")
                self.cache.record_job_status(job, JobStatus.SEEN)
                return True
            # Use is_skipped_blacklist (newly added check)
            if self.cache.is_skipped_blacklist(link):
                logger.debug(f"Skipping: Job previously skipped due to blacklist [{link}]")
                self.cache.record_job_status(job, JobStatus.SEEN)
                return True
            
            # # Use has_failed_application (newly added check)
            # if self.cache.has_failed_application(link):
            #     logger.info(f"Skipping: Job previously failed during application [{link}]")
            #     self.cache.record_job_status(job, JobStatus.SEEN)
            #     return True
            
        # --- End Cache Checks ---
        if self._is_job_state_invalid(job):
            logger.debug(f"Skipping: job card shows state '{job.state}' [{job.link}]")
            if self.cache:
                # ainda assim marcamos como SEEN para não reprocessar no futuro
                self.cache.record_job_status(job, JobStatus.SEEN)
            return True
        
        # --- Blacklist Checks ---
        if self._is_title_blacklisted(job.title):
            logger.debug(f"Skipping: Title '{job.title}' matches title blacklist [{link}]")
            if self.cache: self.cache.record_job_status(job, JobStatus.SKIPPED_BLACKLIST); self.cache.record_job_status(job, JobStatus.SEEN)
            return True
        if self._is_company_blacklisted(job.company):
            logger.debug(f"Skipping: Company '{job.company}' matches company blacklist [{link}]")
            if self.cache: self.cache.record_job_status(job, JobStatus.SKIPPED_BLACKLIST); self.cache.record_job_status(job, JobStatus.SEEN)
            return True
        if self._matches_description_blacklist(job):
            logger.debug(f"Skipping: Job title/description matches description blacklist [{link}]")
            if self.cache: self.cache.record_job_status(job, JobStatus.SKIPPED_LOW_SCORE); self.cache.record_job_status(job, JobStatus.SEEN) # Keep original status for this
            return True
        # --- End Blacklist Checks ---

        # Optional: Filter based on job state/apply method if desired
        # if self._is_apply_method_not_easy_apply(job): ... return True

        logger.debug(f"Job PASSED filters: '{job.title}' at '{job.company}' [{link}]")
        return False # Do not skip

    # --- Helper methods ---
    # (Implementations remain the same)
    def _matches_description_blacklist(self, job: Job) -> bool:
        if not self.description_blacklist_lower: return False
        job_description_lower = job.description.lower() if job.description else ""
        job_title_lower = job.title.lower() if job.title else ""
        for criteria in self.description_blacklist_lower:
            if criteria in job_title_lower or criteria in job_description_lower:
                logger.trace(f"Desc blacklist criteria '{criteria}' found: {job.link}")
                return True
        return False

    def _is_title_blacklisted(self, title: str) -> bool:
        if not title or not self.title_blacklist_set: return False
        title_words = set(word.strip('.,!?;:') for word in title.lower().split())
        intersection = title_words.intersection(self.title_blacklist_set)
        if intersection: logger.trace(f"Blacklisted title words: {intersection}"); return True
        return False

    def _is_company_blacklisted(self, company: str) -> bool:
        if not company or not self.company_blacklist_set: return False
        is_blacklisted = company.strip().lower() in self.company_blacklist_set
        if is_blacklisted: logger.trace(f"Company '{company.strip().lower()}' blacklisted."); return True
        return False
    
    def _is_job_state_invalid(self, job: Job) -> bool:
        return bool(job.state) and job.state.lower() in self.INVALID_STATES