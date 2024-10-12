# job.py
from dataclasses import dataclass
from typing import Optional
from loguru import logger


@dataclass
class Job:
    title: str
    company: str
    location: str
    link: str
    apply_method: str
    state: str = ""
    description: str = ""
    summarize_job_description: str = ""
    pdf_path: str = ""
    recruiter_link: str = ""
    position: str = ""
    score: Optional[float] = None

    def set_summarize_job_description(self, summarize_job_description: str) -> None:
        logger.debug("Setting summarized job description.")
        self.summarize_job_description = summarize_job_description