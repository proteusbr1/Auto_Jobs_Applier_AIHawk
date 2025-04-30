"""
Module for filtering jobs in the AIHawk Job Manager.
"""
from loguru import logger
from src.job import Job


class JobFilter:
    """
    Class for filtering jobs in the AIHawk Job Manager.
    """
    def __init__(self, title_blacklist=None, company_blacklist=None, description_blacklist=None, cache=None):
        """
        Initialize the JobFilter class.

        Args:
            title_blacklist (list, optional): List of blacklisted job title words. Defaults to None.
            company_blacklist (list, optional): List of blacklisted company names. Defaults to None.
            description_blacklist (list, optional): List of criteria that cause a job to be skipped based on description. Defaults to None.
            cache (JobCache, optional): The job cache instance. Defaults to None.
        """
        logger.debug("Initializing JobFilter")
        self.title_blacklist = title_blacklist or []
        self.company_blacklist = company_blacklist or []
        self.description_blacklist = description_blacklist or [] # Store description blacklist

        self.title_blacklist_set = set(word.lower().strip() for word in self.title_blacklist)
        self.company_blacklist_set = set(word.lower().strip() for word in self.company_blacklist)
        # Convert description blacklist criteria to lowercase for case-insensitive matching
        self.description_blacklist_lower = [criteria.lower() for criteria in self.description_blacklist]

        self.cache = cache
        logger.debug("JobFilter initialized successfully")

    def must_be_skipped(self, job: Job) -> bool:
        """
        Determines if a given job should be skipped based on various criteria, including blacklist checks,
        job state, and apply method.

        Args:
            job (Job): The job object to evaluate.

        Returns:
            bool: True if the job should be skipped, False otherwise.
        """
        logger.debug("Checking if job should be skipped.")

        # Extract job information
        job_title = job.title
        company = job.company
        link = job.link

        # Check if the link has already been seen
        if self.cache and self.cache.is_in_is_seen(link):
            logger.debug(f"Skipping by seen link: {link}")
            return True

        # Check if the job has already been skipped for low salary
        if self.cache and self.cache.is_in_skipped_low_salary(job.link):
            logger.debug(f"Job has already been skipped for low salary: {job.link}")
            return True

        # Check if the job has already been skipped for low score (keeping cache name for now)
        if self.cache and self.cache.is_in_skipped_low_score(job.link):
            logger.debug(f"Job has already been skipped for low score: {job.link}")
            return True

        # Check if the job has already been applied
        if self.cache and self.cache.is_in_success(job.link):
            logger.debug(f"Job has already been applied: {job.link}")
            return True

        # Check if job state is Applied, Continue, or Apply
        if self._is_job_state_invalid(job):
            logger.debug(f"Skipping by state: {job.state}")
            return True

        # Check if apply method is not 'Easy Apply'
        if self._is_apply_method_not_easy_apply(job):
            logger.debug(f"Skipping by apply method: {job.apply_method}")
            return True

        # Check Title Blacklist
        if self._is_title_blacklisted(job_title):
            logger.debug(f"Skipping by title blacklist: {job_title}")
            return True

        # Check Company Blacklist
        if self._is_company_blacklisted(company):
            logger.debug(f"Skipping by company blacklist: {company}")
            return True

        # Check Description Blacklist
        if self._matches_description_blacklist(job):
            logger.debug(f"Skipping due to description blacklist match: {job.link}")
            # Add to skipped_low_score cache (keeping the cache name for now)
            if self.cache:
                self.cache.add_to_skipped_low_score(job.link)
            return True

        logger.debug("Job does not meet any skip conditions.")
        return False

    def _matches_description_blacklist(self, job: Job) -> bool:
        """
        Checks if the job title or description contains any of the description blacklist criteria.

        Args:
            job (Job): The job object to evaluate.

        Returns:
            bool: True if any description blacklist criteria is found, False otherwise.
        """
        job_title_lower = job.title.lower()
        job_description_lower = job.description.lower() if job.description else ""

        for criteria in self.description_blacklist_lower:
            if criteria in job_title_lower or criteria in job_description_lower:
                logger.debug(f"Description blacklist criteria '{criteria}' found in job: {job.link}")
                return True
        return False


    def _is_job_state_invalid(self, job: Job) -> bool:
        """
        Checks if the job state is not in the not valid states.

        Args:
            job (Job): The job object to evaluate.

        Returns:
            bool: True if job state is invalid, False otherwise.
        """
        return bool(job.state) and job.state in {"Continue", "Applied", "Apply"}

    def _is_apply_method_not_easy_apply(self, job: Job) -> bool:
        """
        Checks if the apply method is not 'Easy Apply'.

        Args:
            job (Job): The job object to evaluate.

        Returns:
            bool: True if apply method is not 'Easy Apply', False otherwise.
        """
        if job.apply_method is None:
            return False
        return job.apply_method.lower() != "easy apply"

    def _is_title_blacklisted(self, title: str) -> bool:
        """
        Checks if the job title contains any blacklisted words.

        Args:
            title (str): The job title to evaluate.

        Returns:
            bool: True if any blacklisted word is found in the title, False otherwise.
        """
        title_lower = title.lower()
        title_words = set(title_lower.split())
        intersection = title_words.intersection(self.title_blacklist_set)
        is_blacklisted = bool(intersection)

        if is_blacklisted:
            logger.debug(f"Blacklisted words found in title: {intersection}")

        return is_blacklisted

    def _is_company_blacklisted(self, company: str) -> bool:
        """
        Checks if the company name is in the blacklist.

        Args:
            company (str): The company name to evaluate.

        Returns:
            bool: True if the company is blacklisted, False otherwise.
        """
        company_cleaned = company.strip().lower()
        is_blacklisted = company_cleaned in self.company_blacklist_set

        if is_blacklisted:
            logger.debug(f"Company '{company_cleaned}' is in the blacklist.")

        return is_blacklisted
