# src/job_manager/job_applier.py
"""
Handles the process of iterating through filtered jobs and attempting to apply
using an Easy Apply handler component.
"""
from loguru import logger
from typing import List, Optional, Any # Ensure Any is imported

# Ensure correct relative import if job.py is in parent dir
try:
    from ..job import Job, JobCache, JobStatus
except ImportError:
    from src.job import Job, JobCache, JobStatus
# Assuming JobFilter definition is here
from .job_filter import JobFilter
# We no longer need the specific import/alias for the type hint itself
# try:
#     from src.easy_apply import EasyApplyHandler as EasyApplyHandlerType
# except ImportError:
#     logger.error("EasyApplyHandler not found. Check import path.")
#     EasyApplyHandlerType = Any


class JobApplier:
    """
    Applies to a list of jobs after filtering, using a specific application handler
    (e.g., one designed for LinkedIn Easy Apply).
    """
    # Use Any directly in the type hint for the application_handler
    def __init__(self, application_handler: Any, cache: Optional[JobCache] = None): 
        """
        Initializes the JobApplier.

        Args:
            application_handler (Any): Component for executing application steps.
                                       *Must* have a 'main_job_apply' method.
            cache (Optional[JobCache]): The job cache instance for tracking status.
        """
        logger.debug("Initializing JobApplier...")

        # --- Runtime Checks ---
        if application_handler is None:
            raise ValueError("application_handler cannot be None.")

        # Check for the essential method at runtime (Duck Typing)
        # This is the most important check now
        if not hasattr(application_handler, 'main_job_apply'):
             raise AttributeError("Provided application_handler object must have a 'main_job_apply' method.")
        # --- End Runtime Checks ---

        # Check cache type statically
        if cache and not isinstance(cache, JobCache):
            raise TypeError("cache must be JobCache or None")

        self.application_handler = application_handler
        self.cache: Optional[JobCache] = cache
        logger.debug("JobApplier initialized successfully.")

    def apply_jobs(self, job_list: List[Job], job_filter: JobFilter) -> List[Job]:
        """
        Iterates through jobs, filters, and attempts application using the handler.

        Args:
            job_list (List[Job]): List of Job objects extracted from a page.
            job_filter (JobFilter): The filter instance to check if a job should be skipped.

        Returns:
            List[Job]: List of jobs for which an application attempt was successfully initiated.
        """
        if not isinstance(job_filter, JobFilter):
             raise TypeError("job_filter must be an instance of JobFilter")

        applied_jobs_list: List[Job] = []
        total_jobs = len(job_list)
        logger.info(f"Processing {total_jobs} extracted jobs for application...")

        for i, job in enumerate(job_list):
            logger.debug(f"--- Processing Job {i+1}/{total_jobs} ---")
            logger.debug(f"Job Details: Title='{job.title}', Company='{job.company}', Link='{job.link}'")

            # --- Filtering ---
            try:
                if job_filter.must_be_skipped(job):
                    # Log reason handled within must_be_skipped, status recorded there too (SEEN, SKIPPED_*)
                    continue # Move to the next job
            except AttributeError as e:
                 logger.error(f"AttributeError during job filtering for {job.link}, likely missing method in JobCache used by JobFilter: {e}. Skipping job.")
                 if self.cache: self.cache.record_job_status(job, JobStatus.SEEN) # Mark as seen anyway
                 continue
            except Exception as filter_e:
                 logger.error(f"Unexpected error during job filtering for {job.link}: {filter_e}. Skipping job.")
                 if self.cache: self.cache.record_job_status(job, JobStatus.SEEN) # Mark as seen anyway
                 continue
            # --- End Filtering ---

            # --- Application Attempt ---
            was_applied = False # Default to false
            try:
                logger.debug(f"Attempting application process via handler for job: {job.link}")
                # main_job_apply handles internal score/salary checks now
                was_applied = self.application_handler.main_job_apply(job)

                if was_applied:
                    logger.success(f"Application reported as successful by handler for job: {job.link}")
                    applied_jobs_list.append(job)
                    # --- Cache Success (Use record_job_status) ---
                    if self.cache:
                        self.cache.record_job_status(job, JobStatus.SUCCESS)
                        # No need to call SEEN separately if SUCCESS implies SEEN
                else:
                    # main_job_apply returned False (e.g., skipped internally, or failed pre-submit)
                    logger.debug(f"Application handler did not apply for job: {job.link} (skipped based on criteria or failed early).")
                    # Cache as SEEN because it was processed, but not successful application
                    if self.cache:
                         # ** Check if a specific skip status was set on the job object by handler **
                         # Example: if getattr(job, 'skipped_reason', None) == 'low_salary': ... record SKIPPED_LOW_SALARY
                         # Otherwise, just mark as seen.
                         self.cache.record_job_status(job, JobStatus.SEEN)

            except Exception as e:
                # Catch errors during the application attempt itself
                logger.error(f"Application attempt failed for job {job.link} with error: {e}", exc_info=True)
                if self.cache:
                     # Record specific failure status
                     self.cache.record_job_status(job, JobStatus.FAILED_APPLICATION)
                     self.cache.record_job_status(job, JobStatus.SEEN) # Also mark as seen
            # --- End Application Attempt ---

        applied_count = len(applied_jobs_list)
        logger.debug(f"Finished processing job list for this page. Successful applications reported by handler: {applied_count}.")
        return applied_jobs_list