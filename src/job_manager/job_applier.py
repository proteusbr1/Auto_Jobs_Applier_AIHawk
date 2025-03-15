"""
Module for applying to jobs in the AIHawk Job Manager.
"""
import json
from loguru import logger
from src.job import Job


class JobApplier:
    """
    Class for applying to jobs in the AIHawk Job Manager.
    """
    def __init__(self, easy_applier_component, cache=None):
        """
        Initialize the JobApplier class.

        Args:
            easy_applier_component: The AIHawkEasyApplier instance.
            cache (JobCache, optional): The job cache instance. Defaults to None.
        """
        logger.debug("Initializing JobApplier")
        self.easy_applier_component = easy_applier_component
        self.cache = cache
        logger.debug("JobApplier initialized successfully")

    def apply_jobs(self, job_list, job_filter):
        """
        Apply to jobs in the job list.

        Args:
            job_list (list): List of Job objects.
            job_filter (JobFilter): The job filter instance.

        Returns:
            list: List of jobs that were applied to.
        """
        logger.debug(f"Starting to apply to {len(job_list)} jobs.")
        applied_jobs = []

        for job in job_list:
            logger.debug(f"Evaluating job: '{job.title}' at '{job.company}'")

            # Check if the job must be skipped
            if job_filter.must_be_skipped(job):
                logger.debug(f"Skipping job based on filters: {job.link}")
                continue 

            # Check if the job has already been scored
            if self.cache and hasattr(self.cache, 'is_in_job_score') and self.cache.is_in_job_score(job.link):
                logger.debug(f"Job already scored: '{job.title}' at '{job.company}'.")
                job.score = self.get_existing_score(job)
                
            try:
                if self.easy_applier_component.main_job_apply(job):
                    if self.cache:
                        self.cache.write_to_file(job, "success")
                        self.cache.add_to_cache(job, 'success')
                    logger.info(f"Applied: {job.link}")
                    applied_jobs.append(job)

            except Exception as e:
                logger.error(
                        f"Failed to apply for job: Title='{job.title}', Company='{job.company}', "
                        f"Location='{job.location}', Link='{job.link}', Job State='{job.state}', Apply Method='{job.apply_method}', "
                        f"Error: {e}"
                    )

            # Add job link to seen jobs set
            if self.cache:
                self.cache.add_to_cache(job, "is_seen")

        logger.debug(f"Applied to {len(applied_jobs)} jobs.")
        return applied_jobs

    def get_existing_score(self, job):
        """
        Retrieves the existing score for the job from the job_score.json file.

        Args:
            job (Job): The job object.

        Returns:
            float: The job score, or 0 if not found.
        """
        if not self.cache or not hasattr(self.cache, 'output_file_directory'):
            return 0
            
        file_path = self.cache.output_file_directory / 'job_score.json'
        link = job.link
        
        if not file_path.exists():
            return 0  # Return a default low score if file does not exist

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                scored_jobs = json.load(f)
                for scored_job in scored_jobs:
                    if scored_job.get('link') == link:
                        return scored_job.get('score', 0)  # Return existing score or 0 if not found
        except json.JSONDecodeError:
            logger.warning("job_score.json is corrupted. Returning score as 0.")
            return 0
        except Exception as e:
            logger.error(f"Error reading job_score.json: {e}", exc_info=True)
            return 0
