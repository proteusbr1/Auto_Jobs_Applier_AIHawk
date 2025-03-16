"""
Class responsible for handling interactions with the AI model to answer questions,
evaluate jobs, and manage resumes.
"""

import re
import textwrap
from datetime import datetime
from typing import Dict, List, Optional, Union

from Levenshtein import distance
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from loguru import logger
import src.strings as strings
from src.job import Job
from src.llm.adapter import AIAdapter
from src.llm.logger import LoggerChatModel
from data_folder.personal_info import USER_RESUME_CHATGPT, COMPANY_CAPABILITIES
from app_config import (
    MIN_SCORE_APPLY,
    SALARY_EXPECTATIONS,
    USE_JOB_SCORE,
    USE_SALARY_EXPECTATIONS,
    TRYING_DEGUB,
)

if TRYING_DEGUB:
    SALARY_EXPECTATIONS = 0
    MIN_SCORE_APPLY = 0


class GPTAnswerer:
    """
    Class responsible for handling interactions with the AI model to answer questions,
    evaluate jobs, and manage resumes.
    """

    def __init__(self, config: Dict, llm_api_key: str):
        """
        Initialize the GPTAnswerer with the given configuration and API key.

        Args:
            config (Dict): Configuration dictionary containing model details.
            llm_api_key (str): The API key for the AI model.
        """
        self.ai_adapter = AIAdapter(config, llm_api_key)
        self.llm_cheap = LoggerChatModel(self.ai_adapter)
        self.job = None
        self.resume_summary = self.format_resume(USER_RESUME_CHATGPT)
        logger.debug("GPTAnswerer initialized.")

    @property
    def job_description(self):
        """
        Get the job description from the current job.

        Returns:
            str: The description of the current job.
        """
        return self.job.description

    @staticmethod
    def find_best_match(text: str, options: List[str]) -> str:
        """
        Find the best matching option from a list based on Levenshtein distance.

        Args:
            text (str): The text to match against the options.
            options (List[str]): A list of possible options.

        Returns:
            str: The option that best matches the input text.

        Raises:
            Exception: If an error occurs during the matching process.
        """
        logger.debug(f"Finding best match for text: '{text}' in options: {options}")
        try:
            distances = [(option, distance(text.lower(), option.lower())) for option in options]
            best_option = min(distances, key=lambda x: x[1])[0]
            logger.debug(f"Best match found: {best_option}")
            return best_option
        except Exception as e:
            logger.error(f"Error finding best match: {e}")
            raise

    @staticmethod
    def _preprocess_template_string(template: str) -> str:
        """
        Preprocess a template string by dedenting it.

        Args:
            template (str): The template string to preprocess.

        Returns:
            str: The preprocessed template string.
        """
        logger.debug("Preprocessing template string.")
        processed = textwrap.dedent(template)
        logger.debug("Template string preprocessed.")
        return processed

    def set_resume(self, resume):
        logger.debug(f"Setting resume: {resume}")
        self.resume = resume

    def set_job(self, 
                title: str, 
                company: str, 
                location: str, 
                link: str, 
                apply_method: str,
                salary: Optional[str] = "",
                description: Optional[str] = "", 
                recruiter_link: Optional[str] = "",
                gpt_salary: Optional[float] = None,
                search_country: Optional[str] = None,
                ):
        """
        Set the job details for the GPTAnswerer.

        Args:
            title (str): The job title.
            company (str): The company offering the job.
            location (str): The job location.
            link (str): The link to the job posting.
            apply_method (str): The method to apply for the job.
            description (Optional[str], optional): The job description. Defaults to "".
            recruiter_link (Optional[str], optional): The recruiter's link. Defaults to "".

        Raises:
            ValueError: If any required job attributes are missing.
        """
        logger.debug(f"Setting job with title: {title}, company: {company}, location: {location}, "
                     f"link: {link}, apply_method: {apply_method}, recruiter_link: {recruiter_link}")

        missing_attributes = []
        if not title:
            missing_attributes.append("title")
        if not company:
            missing_attributes.append("company")
        if not location:
            missing_attributes.append("location")
        if not link:
            missing_attributes.append("link")
        if not apply_method:
            missing_attributes.append("apply_method")

        if missing_attributes:
            logger.error(f"Missing job attributes: {', '.join(missing_attributes)}")
            raise ValueError(f"Missing job attributes: {', '.join(missing_attributes)}")

        self.job = Job(
            title=title,
            company=company,
            location=location,
            link=link,
            apply_method=apply_method,
            salary=salary,
            description=description,
            recruiter_link=recruiter_link,
            gpt_salary=gpt_salary,
            search_country=search_country,
        )
        logger.debug(f"Job object set: {self.job}")

    def set_job_application_profile(self, job_application_profile):
        logger.debug(f"Setting job application profile: {job_application_profile}")
        self.job_application_profile = job_application_profile

    def _create_chain(self, template: str):
        """
        Create a prompt chain using the given template.

        Args:
            template (str): The template string for the prompt.

        Returns:
            The created prompt chain.

        Raises:
            Exception: If an error occurs while creating the chain.
        """
        logger.debug(f"Creating chain with template: {template}")
        try:
            prompt = ChatPromptTemplate.from_template(template)
            chain = prompt | self.llm_cheap | StrOutputParser()
            logger.debug("Chain created successfully.")
            return chain
        except Exception as e:
            logger.error(f"Error creating chain: {e}")
            raise

    def answer_question_numeric(self, question: str, default_experience: int = 3) -> int:
        """
        Answer a numeric question by extracting a number from the AI model's response.

        Args:
            question (str): The question to answer.
            default_experience (int, optional): The default value to return if extraction fails. Defaults to 3.

        Returns:
            int: The extracted number or the default value if extraction fails.

        Raises:
            Exception: If an error occurs during the process.
        """
        logger.debug(f"Answering numeric question: {question}")
        try:
            func_template = self._preprocess_template_string(strings.numeric_question_template)
            prompt = ChatPromptTemplate.from_template(func_template)
            chain = prompt | self.llm_cheap | StrOutputParser()
            output_str = chain.invoke({
                "resume_educations": self.resume.education_details,
                "resume_jobs": self.resume.experience_details,
                "resume_projects": self.resume.projects,
                "question": question
            })
            logger.debug(f"Raw output for numeric question: {output_str}")
            output = self.extract_number_from_string(output_str)
            logger.debug(f"Extracted number: {output}")
            return output
        except ValueError:
            logger.warning(f"Failed to extract number, using default experience: {default_experience}")
            return default_experience
        except Exception as e:
            logger.error(f"Error answering numeric question: {e}")
            raise

    def extract_number_from_string(self, output_str: str) -> int:
        """
        Extract the first number found in the given string.

        Args:
            output_str (str): The string from which to extract the number.

        Returns:
            int: The extracted number.

        Raises:
            ValueError: If no number is found in the string.
        """
        logger.debug(f"Extracting number from string: {output_str}")
        numbers = re.findall(r"\d+", output_str)
        if numbers:
            number = int(numbers[0])
            logger.debug(f"Numbers found: {numbers}. Extracted number: {number}")
            return number
        else:
            logger.error("No numbers found in the string.")
            raise ValueError("No numbers found in the string.")

    def answer_question_from_options(self, question: str, options: List[str]) -> str:
        """
        Answer a multiple-choice question by selecting the best matching option.

        Args:
            question (str): The question to answer.
            options (List[str]): A list of possible answer options.

        Returns:
            str: The best matching option.

        Raises:
            Exception: If an error occurs during the process.
        """
        logger.debug(f"Answering question from options: {question}")
        try:
            func_template = self._preprocess_template_string(strings.options_template)
            prompt = ChatPromptTemplate.from_template(func_template)
            chain = prompt | self.llm_cheap | StrOutputParser()
            output_str = chain.invoke({"resume": self.resume, "question": question, "options": options})
            logger.debug(f"Raw output for options question: {output_str}")
            best_option = self.find_best_match(output_str, options)
            logger.debug(f"Best option determined: {best_option}")
            return best_option
        except Exception as e:
            logger.error(f"Error answering question from options: {e}")
            raise

    def resume_or_cover(self, phrase: str) -> str:
        """
        Determine whether a given phrase refers to a resume or a cover letter.

        Args:
            phrase (str): The phrase to evaluate.

        Returns:
            str: 'resume' or 'cover' based on the evaluation.

        Raises:
            Exception: If an error occurs during the process.
        """
        logger.debug(f"Determining if phrase refers to resume or cover letter: '{phrase}'")
        try:
            prompt_template = """
                Given the following phrase, respond with only 'resume' if the phrase is about a resume, or 'cover' if it's about a cover letter.
                If the phrase contains only one word 'upload', consider it as 'cover'.
                If the phrase contains 'upload resume', consider it as 'resume'.
                Do not provide any additional information or explanations.

                phrase: {phrase}
                """
            prompt = ChatPromptTemplate.from_template(prompt_template)
            chain = prompt | self.llm_cheap | StrOutputParser()
            response = chain.invoke({"phrase": phrase})
            logger.debug(f"Response for resume_or_cover: {response}")

            if "resume" in response.lower():
                return "resume"
            elif "cover" in response.lower():
                return "cover"
            else:
                logger.warning("Unable to determine if phrase refers to resume or cover letter. Defaulting to 'resume'.")
                return "resume"
        except Exception as e:
            logger.error(f"Error determining resume or cover letter: {e}")
            raise

    def ask_chatgpt(self, prompt: str) -> str:
        """
        Send a prompt to ChatGPT and retrieve the response.

        Args:
            prompt (str): The prompt to send to ChatGPT.

        Returns:
            str: The content of the response from ChatGPT.

        Raises:
            Exception: If an error occurs while communicating with ChatGPT.
        """
        logger.debug(f"Sending prompt to ChatGPT: {prompt}")
        try:
            # Format the prompt as a list of messages
            formatted_prompt = [{"role": "user", "content": prompt}]

            # Pass the formatted prompt to the model
            response = self.llm_cheap(formatted_prompt)
            logger.debug(f"Received response: {response}")

            # Check if the response is in the expected format
            if hasattr(response, 'content'):
                content = response.content
                if content:
                    logger.debug(f"Returning content: {content}")
                    return content
                else:
                    logger.error("No content found in response.")
                    return "No content returned from ChatGPT."
            elif isinstance(response, dict) and 'content' in response:
                content = response['content']
                if content:
                    logger.debug(f"Returning content from dict: {content}")
                    return content
                else:
                    logger.error("No content found in response dictionary.")
                    return "No content returned from ChatGPT."
            else:
                logger.error(f"Unexpected response format: {response}")
                return "Unexpected response format from ChatGPT."
        except Exception as e:
            logger.error(f"Error while getting response from ChatGPT: {e}")
            raise

    def evaluate_job(self, job: Job) -> float:
        """
        Evaluate the compatibility between a job description and a resume.

        Args:
            job (Job): The job to evaluate against.
            resume_prompt (str): The resume content to evaluate.

        Returns:
            float: A score from 0 to 10 representing the compatibility.

        Raises:
            Exception: If an error occurs during the evaluation.
        """
        """
        Sends the job description and resume to the AI system and returns a score from 0 to 10.
        """
        job_description = job.description
        job_title = job.title
        job_salary = job.salary
        resume_summary = self.resume_summary
        location = job.location

        # Create the prompt for evaluating the job and resume
        personal_prompt = f"""
        You are a Human Resources expert specializing in evaluating job applications for the {location} job market. Your task is to assess the compatibility between the following job description and a provided resume. 
        Return only a score from 0 to 10 representing the candidate's likelihood of securing the position, with 0 being the lowest probability and 10 being the highest. 
        The assessment should consider HR-specific criteria for the {location} job market, including skills, experience, education, and any other relevant criteria mentioned in the job description.

        Job Title: 
        ({job_title})

        Job Salary:
        ({job_salary})

        Job Description:
        ({job_description})

        My Resume:
        ({resume_summary})

        Score (0 to 10):
        """

        company_prompt = f"""
        You are a business development expert specializing in connecting companies with suitable job opportunities in the {location} market. I am searching for job listings on LinkedIn to identify opportunities to expand my company. My goal is to find promising opportunities to offer our services to the companies that are hiring.

        Your task is to assess the compatibility between the following job description and my company's capabilities.

        Please return only a score from 0 to 10, representing the probability that my company can successfully secure and execute the job, where 0 is the lowest probability and 10 is the highest.

        The assessment should consider criteria such as required skills, experience, resources, certifications, and any other relevant factors mentioned in the job description.

        Job Title:
        ({job_title})

        Job Salary:
        ({job_salary})

        Job Description:
        ({job_description})

        Company Capabilities:
        ({COMPANY_CAPABILITIES})

        Score (0 to 10):
        """     
        
        prompt = personal_prompt
        
        logger.debug("Sending job description and resume to GPT for evaluation")

        # Use the function ask_chatgpt to perform the evaluation
        try:
            response = self.ask_chatgpt(prompt)
            logger.debug(f"Received response from GPT: {response}")

            # Process the response to extract the score
            match = re.search(r"\b(\d+(\.\d+)?)\b", response)
            if match:
                score = float(match.group(1))
                if 0 <= score <= 10:
                    logger.debug(f"Extracted score from GPT response: {score}")
                    return score
                else:
                    logger.error(f"Score out of expected range (0-10): {score}")
                    return 0.1  # Returns 0.0 if the score is out of the expected range
            else:
                logger.error(f"Could not find a valid score in response: {response}")
                return 0.1  # Returns 0.1 if no valid score is found

        except Exception as e:
            logger.error(f"Error processing the score from response: {e}", exc_info=True)
            return 0.1  # Returns 0.1 in case of an error

    def estimate_salary(self, job: Job) -> float:
        """
        Estimate the salary that might be offered to the user for a given job, based on the job description and resume.
        
        Args:
            job (Job): The job object containing the job description.
            resume_summary (str): The user's resume summary.
        
        Returns:
            float: The estimated salary.
        """
        logger.debug("Estimating salary based on job description and resume.")
        try:
            resume_summary = self.resume_summary
            salary_expectation_line = f"salary expectation: {SALARY_EXPECTATIONS}\n"
            resume_summary = f"{salary_expectation_line}{resume_summary}"
            location = job.location
            job_salary = job.salary 
            
            # Create the prompt to ask ChatGPT
            prompt = f"""
             You are a Human Resources expert specializing in evaluating job applications for the {location} job market.
             Given the job description and the candidate's resume below, estimate the annual salary in US dollars that the employer is likely to offer to this candidate. 
             Provide your answer as a single number, representing the annual salary in US dollars, without any additional text, units, currency symbols, or ranges. 
             If the salary is given as a range, return only the highest value in the range. Do not include any explanations.

            Job Title:
            ({job.title})

            Job Salary:
            ({job_salary})

            Job Description:
            ({job.description})

            My Resume:
            ({resume_summary})

            Estimated annual Salary (in US dollars):
            """

            # Use the function ask_chatgpt to get the estimated salary
            response = self.ask_chatgpt(prompt)
            logger.debug(f"Received salary estimation from GPT: {response}")

            # Process the response to extract the salary
            # Remove any non-digit characters except for periods and commas
            salary_str = re.sub(r'[^\d.,]', '', response)
            # Replace commas with nothing
            salary_str = salary_str.replace(',', '')

            # If the salary_str contains a range (e.g., "70000-90000"), split and take the highest value
            if '-' in salary_str:
                parts = salary_str.split('-')
                # Take the highest value
                highest_salary = max(float(part.strip()) for part in parts if part.strip())
                logger.debug(f"Extracted highest salary from range: {highest_salary}")
                return highest_salary
            else:
                # Convert to float
                salary = float(salary_str)
                logger.debug(f"Extracted salary: {salary}")
                return salary

        except Exception as e:
            logger.error(f"Error estimating salary: {e}", exc_info=True)
            return 0.1  # Return 0.0 in case of an error

    def answer_question_date(self, question: str) -> datetime:
        """
        Generate an appropriate date based on the given question using ChatGPT.

        Args:
            question (str): The question to analyze.

        Returns:
            datetime: A datetime object representing the generated date.
        """
        logger.debug(f"Answering date question: {question}")
        try:
            # Prepare the prompt using the date_question_template
            func_template = self._preprocess_template_string(strings.date_question_template)
            prompt = ChatPromptTemplate.from_template(func_template)
            chain = prompt | self.llm_cheap | StrOutputParser()
            # Get today's date in YYYY-MM-DD format
            today_date_str = datetime.now().strftime("%Y-%m-%d")
            # Invoke the chain with the question and today's date
            output_str = chain.invoke({"question": question, "today_date": today_date_str})
            logger.debug(f"Raw output for date question: {output_str}")

            # Extract the date from the output
            date_str = output_str.strip()
            try:
                # Parse the date string into a datetime object
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
                logger.debug(f"Parsed date: {parsed_date}")
                return parsed_date
            except ValueError:
                logger.error(f"Failed to parse date from output: {date_str}")
                raise ValueError(f"Could not parse date from GPT output: {date_str}")
        except Exception as e:
            logger.error(f"Error answering date question: {e}", exc_info=True)
            # In case of an error, return today's date as a fallback
            return datetime.now()

    def answer_question_simple(self, question: str, job: Job, limit_caractere: int = 140) -> str:
        """
        Answers questions based on the resume and the provided job.
        
        Args:
            question (str): The question to be answered.
            job (Job): The Job object related to the question.
            limit_caractere (int, optional): The maximum character limit for the answer. Defaults to 140.
        
        Returns:
            str: The answer generated by the model.
        
        Raises:
            Exception: If an error occurs during the invocation of the model.
        """
        logger.debug(f"Answering simple question: {question}")
        
        # Use a more restrictive character limit for the "Headline" field
        if question.lower() == "headline":
            limit_caractere = 124
            logger.debug(f"Using restricted character limit of {limit_caractere} for Headline field")
        
        try:
            # Ensure the job is defined
            if job:
                logger.debug(f"Setting job information: {job.title} at {job.company}")
                self.set_job(
                    title=job.title,
                    company=job.company,
                    location=job.location,
                    link=job.link,
                    apply_method=job.apply_method,
                    salary=job.salary,
                    description=job.description,
                    recruiter_link=job.recruiter_link,
                    search_country=job.search_country,
                )
            else:
                logger.error("The 'job' parameter is None.")
                raise ValueError("The 'job' parameter cannot be None.")
            
            if self.job is None:
                logger.error("Job object is None. Configure the job first using set_job().")
                raise ValueError("Job object is None. Configure the job first using set_job().")
            
            # Create the prompt following the specified rules
            prompt_template = """
            You are an AI assistant specializing in human resources and knowledgeable about the {location} job market. Your role is to help me secure a job by answering questions related to my resume and a job description. Follow these rules:
            - Answer questions directly.
            - Keep the answer under {limit_caractere} characters.
            - If not sure, provide an approximate answer.

            Job Title:
            ({job_title})

            Job Salary:
            ({job_salary})

            Job Description:
            ({job_description})

            Resume:
            ({resume})

            Question:
            ({question})

            Answer:
            """
            
            # Prepare the prompt with the necessary information
            prompt = ChatPromptTemplate.from_template(prompt_template)
            formatted_prompt = prompt.format(
                limit_caractere=limit_caractere,
                job_title=self.job.title,
                job_salary=self.job.salary,
                job_description=self.job.description,
                resume=self.resume_summary,
                question=question,
                location=self.job.location,
            )
            
            # Invoke the model
            response = self.ai_adapter.invoke(formatted_prompt)
            logger.debug(f"Response received from the model: {response.content}")
            
            # Extract the content from the response
            if hasattr(response, 'content'):
                answer = response.content.strip()
            elif isinstance(response, dict) and 'content' in response:
                answer = response['content'].strip()
            else:
                logger.error(f"Unexpected response format: {response}")
                raise ValueError("Unexpected response format from the model.")
            
            # Ensure the answer is within the character limit
            if len(answer) > limit_caractere:
                answer = answer[:limit_caractere - 3] + "..."
                logger.debug(f"Answer truncated to {limit_caractere} characters: {answer}")
            
            return answer
        
        except Exception as e:
            logger.error(f"Error answering the simple question: {e}", exc_info=True)
            raise

    def format_resume(self, resume_summary: str) -> str:
        """
        Prepends today's date to the resume summary.

        Args:
            resume_summary (str): The original resume summary.
            
        Returns:
            str: The updated resume summary with today's date at the beginning.
        """
        today_date = datetime.now().strftime("%Y-%m-%d")
        date_line = f"today date: {today_date} YYYY-MM-DD\n"
        updated_resume = f"{date_line}{resume_summary}"
        return updated_resume
    
    def extract_keywords_from_job_description(self, job_description: str) -> List[str]:
        """
        Extracts key keywords from the given job description that HR programs or bots would use to evaluate resumes.
        
        Args:
            job_description (str): The job description text.
        
        Returns:
            List[str]: A list of extracted keywords.
        
        Raises:
            ValueError: If the extracted keywords are not in the expected format.
            Exception: For any other unforeseen errors.
        """
        logger.info("Extracting keywords from job description.")
        try:
            prompt = (
                "Extract the most important keywords from the following job description that HR systems "
                "or automated bots would use to evaluate and rank resumes. Return the keywords as a JSON list. Return de JSON list and noting else."
                "\n\nJob Description:\n"
                f"({job_description})"
                "\n\nKeywords:"
            )
            
            response = self.ask_chatgpt(prompt)
            logger.debug(f"Raw response from GPT: {response}")
            
            # Use regex to find JSON-like list in the response
            keywords_match = re.search(r'\[.*?\]', response, re.DOTALL)
            if not keywords_match:
                logger.error("Failed to extract keywords list from GPT response.")
                raise ValueError("GPT response does not contain a valid keywords list.")
            
            keywords_str = keywords_match.group(0)
            logger.debug(f"Extracted keywords string: {keywords_str}")
            
            # Clean and parse the keywords string
            # Remove any surrounding quotes or unwanted characters
            keywords = re.findall(r"'(.*?)'|\"(.*?)\"", keywords_str)
            # Flatten the list and remove empty strings
            keywords = [kw for pair in keywords for kw in pair if kw]
            logger.debug(f"Parsed keywords list: {keywords}")
            
            if not isinstance(keywords, list) or not all(isinstance(kw, str) for kw in keywords):
                logger.error("Extracted keywords are not in the expected list of strings format.")
                raise ValueError("Extracted keywords are not in the expected list of strings format.")
            
            logger.info(f"Successfully extracted {len(keywords)} keywords.")
            return keywords
        
        except ValueError as ve:
            logger.exception(f"Value error during keyword extraction: {ve}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error during keyword extraction: {e}")
            raise

    def generate_summary_based_on_keywords(self, resume: str, resume_summary: str, keywords: List[str]) -> str:
        """
        Generates a tailored resume summary based on the provided resume, resume summary, and extracted keywords.
        
        Args:
            resume (str): The full resume content.
            resume_summary (str): The original resume summary.
            keywords (List[str]): The list of keywords extracted from the job description.
        
        Returns:
            str: The tailored resume summary.
        
        Raises:
            ValueError: If inputs are invalid.
            Exception: For any other unforeseen errors.
        """
        logger.info("Generating tailored resume summary based on extracted keywords.")
        try:
            # Join the keywords into a comma-separated string
            keywords_str = ', '.join(keywords)
            
            # Refined prompt without the "Tailored Resume Summary:" label
            prompt = (
                "Using the following resume, resume summary, and keywords extracted from a job description, "
                "create a concise and professional tailored resume summary that highlights the most relevant skills and experiences "
                "to increase the likelihood of passing through HR evaluation systems. Ensure the summary is truthful "
                "and only includes information provided. Incorporate the keywords appropriately without fabricating or exaggerating any information."
                "\n\nOld Resume Summary:\n"
                f"({resume_summary})"
                "\n\nResume:\n"
                f"({resume})"
                "\n\nKeywords:\n"
                f"({keywords_str})"
                "\n\nPlease provide the tailored resume summary below without any headings or labels:"
            )
            
            # Send the prompt to ChatGPT
            response = self.ask_chatgpt(prompt)
            logger.debug(f"Raw response from GPT for tailored summary: {response}")
            
            # Clean the response by stripping leading/trailing whitespace
            tailored_summary = response.strip()
            
            # Validate the response
            if not tailored_summary:
                logger.error("GPT did not return a tailored summary.")
                raise ValueError("GPT did not return a tailored summary.")
            
            logger.info("Tailored resume summary generated successfully.")
            return tailored_summary
        
        except ValueError as ve:
            logger.exception(f"Value error during summary generation: {ve}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error during summary generation: {e}")
            raise

    def generate_cover_letter_based_on_keywords(self, job_description: str, resume: str, keywords: List[str]) -> str:
        """
        Generates a tailored cover letter based on the job description, resume, and extracted keywords.
        
        Args:
            job_description (str): The job description text.
            resume (str): The full resume content.
            keywords (List[str]): The list of keywords extracted from the job description.
        
        Returns:
            str: The tailored cover letter.
        
        Raises:
            ValueError: If inputs are invalid.
            Exception: For any other unforeseen errors.
        """
        logger.info("Generating tailored cover letter.")
        try:
            keywords_str = ', '.join(keywords)
            prompt = (
                "Using the following job description, resume, and keywords, compose a concise and professional cover letter that emphasizes the most relevant skills and experiences. "
                "Ensure the cover letter is truthful and only includes information provided. Incorporate the keywords appropriately without fabricating or exaggerating any information. "
                "The cover letter should not exceed 300 words and should be written in paragraph form."
                "\n\nJob Description:\n"
                f"({job_description})"
                "\n\nResume:\n"
                f"({resume})"
                "\n\nKeywords:\n"
                f"({keywords_str})"
                "\n\nPlease provide the Cover Letter: below without any headings or labels:"
            )
            
            cover_letter = self.ask_chatgpt(prompt)
            logger.debug(f"Tailored Cover Letter: {cover_letter}")
            return cover_letter.strip()
        
        except Exception as e:
            logger.error(f"Error generating tailored cover letter: {e}", exc_info=True)
            raise
