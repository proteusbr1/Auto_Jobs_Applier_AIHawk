# job.py
from dataclasses import dataclass
from typing import Optional, Set
from loguru import logger
import json
from pathlib import Path
from datetime import datetime


@dataclass
class Job:
    title: str
    company: str
    location: str
    link: str
    apply_method: str
    state: str = ""
    salary: str = ""
    description: str = ""
    summarize_job_description: str = ""
    pdf_path: str = ""
    cover_letter_path: str = ""
    recruiter_link: str = ""
    position: str = ""
    score: Optional[float] = None
    gpt_salary: Optional[float] = None

    def set_summarize_job_description(self, summarize_job_description: str) -> None:
        logger.debug("Setting summarized job description.")
        self.summarize_job_description = summarize_job_description


class JobCache:
    def __init__(self, output_file_directory):
        logger.debug("Initializing JobCache")
        self.output_file_directory = output_file_directory
        self.job_score_cache: Set[str] = set()
        self.skipped_low_salary_cache: Set[str] = set()
        self.skipped_low_score_cache: Set[str] = set()
        self.success_cache: Set[str] = set()
        self.is_seen_cache: Set[str] = set()
        self._load_all_jsons()
        logger.debug("JobCache initialized successfully")

    def _load_all_jsons(self):
        logger.debug("JobCache loading all JSON files")
        json_files = {
            'job_score.json': 'job_score_cache',
            'skipped_low_salary.json': 'skipped_low_salary_cache',
            'skipped_low_score.json': 'skipped_low_score_cache',
            'success.json': 'success_cache'
        }

        for file_name, cache_attr in json_files.items():
            file_path = self.output_file_directory / file_name
            if file_path.exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        jobs = json.load(f)
                        if isinstance(jobs, list):
                            links = {job.get('link') for job in jobs if 'link' in job}
                            getattr(self, cache_attr).update(links)
                            logger.info(f"Loaded {len(links)} links from {file_name} into {cache_attr}")
                        else:
                            logger.warning(f"Unexpected format in {file_name}. Expected a list.")
                except json.JSONDecodeError:
                    logger.warning(f"{file_name} is corrupted. Ignoring this file.")
                except Exception as e:
                    logger.error(f"Error reading {file_name}: {e}", exc_info=True)
            else:
                logger.debug(f"{file_name} not found. Ignoring.")

    def is_in_job_score(self, link: str) -> bool:
        in_cache = link in self.job_score_cache
        logger.debug(f"Checking if link '{link}' is in job_score_cache: {in_cache}")
        return in_cache

    def is_in_skipped_low_salary(self, link: str) -> bool:
        in_cache = link in self.skipped_low_salary_cache
        logger.debug(f"Checking if link '{link}' is in skipped_low_salary_cache: {in_cache}")
        return in_cache

    def is_in_skipped_low_score(self, link: str) -> bool:
        in_cache = link in self.skipped_low_score_cache
        logger.debug(f"Checking if link '{link}' is in skipped_low_score_cache: {in_cache}")
        return in_cache

    def is_in_success(self, link: str) -> bool:
        in_cache = link in self.success_cache
        logger.debug(f"Checking if link '{link}' is in success_cache: {in_cache}")
        return in_cache

    def is_in_is_seen(self, link: str) -> bool:
        in_cache = link in self.is_seen_cache
        logger.debug(f"Checking if link '{link}' is in is_seen_cache: {in_cache}")
        return in_cache

    def add_to_cache(self, job, cache_type: str):
        logger.debug(f"Adding link '{job.link}' to cache type '{cache_type}'")
        cache_mapping = {
            'job_score': ('job_score_cache', 'job_score.json'),
            'skipped_low_salary': ('skipped_low_salary_cache', 'skipped_low_salary.json'),
            'skipped_low_score': ('skipped_low_score_cache', 'skipped_low_score.json'),
            'success': ('success_cache', 'success.json'),
            'is_seen': ('is_seen_cache', 'is_seen.json'),
        }

        if cache_type not in cache_mapping:
            logger.error(f"Unknown cache type: {cache_type}")
            return

        cache_attr, file_name = cache_mapping[cache_type]
        cache_set = getattr(self, cache_attr)
        cache_set.add(job.link)

    def write_to_file(self, job, file_name):
        logger.debug(f"Writing job application result to file: '{file_name}'.")
        pdf_path = Path(job.pdf_path).resolve()
        pdf_path = pdf_path.as_uri()
        
        # Get current date and time
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        data = {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "link": job.link,
            "apply_method": job.apply_method,
            "state": job.state,
            "salary": job.salary,
            # "description": job.description,
            # "summarize_job_description": job.summarize_job_description,	
            "pdf_path": pdf_path,
            "recruiter_link": job.recruiter_link,
            "search_term": job.position,
            "score": job.score,  
            "gpt_salary": job.gpt_salary,
            "timestamp": current_time
        }
        
        file_path = Path("data_folder") / "output" / f"{file_name}.json"
        
        if not file_path.exists():
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump([data], f, indent=4)
                logger.debug(f"Job data written to new file: '{file_name}'.")
            except Exception as e:
                logger.error(f"Failed to write to new file '{file_name}': {e}", exc_info=True)
        else:
            try:
                with open(file_path, 'r+', encoding='utf-8') as f:
                    try:
                        existing_data = json.load(f)
                    except json.JSONDecodeError:
                        logger.error(f"JSON decode error in file: {file_path}. Initializing with empty list.")
                        existing_data = []
                    
                    existing_data.append(data)
                    f.seek(0)
                    json.dump(existing_data, f, indent=4)
                    f.truncate()
                logger.debug(f"Job data appended to existing file: '{file_name}'.")
            except Exception as e:
                logger.error(f"Failed to append to file '{file_name}': {e}", exc_info=True)