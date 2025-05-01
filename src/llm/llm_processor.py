# src/llm/llm_processor.py
"""
Core class for processing tasks using a Large Language Model (LLM).

This class interacts with an LLM (via a `LoggingModelWrapper`) to perform
various NLP tasks such as answering questions based on context (resume, job description),
evaluating job compatibility, estimating salary, generating summaries, and more.
It utilizes predefined prompt templates and helper functions.
"""

import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Union, Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage # Import for type hinting

from loguru import logger

# Assuming strings are now better organized, perhaps in a dedicated prompts module
import src.llm.prompts as prompt_strings # Or from .prompts import ...
from src.job import Job # Assuming Job class definition exists

# Import the wrapper and utilities
from .interaction_logger import LoggingModelWrapper
from .utils.helpers import (
    find_best_match,
    preprocess_template_string,
    extract_number_from_string,
    format_datetime
)
from .exceptions import LLMError, LLMInvocationError, LLMParsingError, ConfigurationError
from app_config import SALARY_EXPECTATIONS, MIN_SCORE_APPLY, TRYING_DEBUG

# Conditional assignment based on debug flag (this logic might belong higher up in app setup)
if TRYING_DEBUG:
    EFFECTIVE_SALARY_EXPECTATIONS = 0.0
    EFFECTIVE_MIN_SCORE_APPLY = 0.0
else:
    EFFECTIVE_SALARY_EXPECTATIONS = SALARY_EXPECTATIONS
    EFFECTIVE_MIN_SCORE_APPLY = MIN_SCORE_APPLY


class LLMProcessor:
    """
    Handles interactions with an LLM to perform specific job application related tasks.

    Uses prompt templates and context (resume, job details) to generate answers,
    evaluations, and other required text, leveraging an underlying LLM wrapper
    that handles invocation, logging, and basic error handling.
    """

    # Default character limit for simple answers, can be overridden
    DEFAULT_ANSWER_CHAR_LIMIT = 140
    HEADLINE_CHAR_LIMIT = 124 # Specific limit for headline field

    def __init__(
        self,
        llm_wrapper: LoggingModelWrapper,
        resume_content: str,
        salary_expectations: Optional[float] = None,
        min_score_to_apply: Optional[float] = None,
        # Add other dependencies like job_application_profile if needed
        # job_application_profile: Optional[Any] = None
    ):
        """
        Initializes the LLMProcessor.

        Args:
            llm_wrapper (LoggingModelWrapper): An initialized wrapper containing the AI model.
            resume_content (str): The plain text content of the resume (already extracted from HTML).
            salary_expectations (Optional[float]): User's target salary. Defaults to a predefined value.
            min_score_to_apply (Optional[float]): Minimum job score threshold. Defaults to a predefined value.
            # job_application_profile (Optional[Any]): User's application profile data.
        """
        if not isinstance(llm_wrapper, LoggingModelWrapper):
             raise TypeError("llm_wrapper must be an instance of LoggingModelWrapper")
        if not isinstance(resume_content, str) or not resume_content:
             raise ValueError("resume_content must be a non-empty string")

        self.llm = llm_wrapper # The logging wrapper instance
        self._raw_resume = resume_content # Store the plain text resume
        self.formatted_resume = self._format_resume_with_date(self._raw_resume) # Pre-format resume with date
        self.salary_expectations = salary_expectations if salary_expectations is not None else EFFECTIVE_SALARY_EXPECTATIONS
        self.min_score_to_apply = min_score_to_apply if min_score_to_apply is not None else EFFECTIVE_MIN_SCORE_APPLY
        # self.job_application_profile = job_application_profile

        self.current_job: Optional[Job] = None # Holds the job currently being processed

        logger.info("LLMProcessor initialized.")
        logger.info(f"Salary Expectation set to: {self.salary_expectations}")
        logger.info(f"Min Score to Apply set to: {self.min_score_to_apply}")


    def _format_resume_with_date(self, resume_summary: str) -> str:
        """
        Prepends the current date to the resume summary.

        Args:
            resume_summary (str): The original resume summary as plain text.

        Returns:
            str: The resume summary prefixed with "today date: YYYY-MM-DD".
        """
        today_date_str = format_datetime(datetime.now(), "%Y-%m-%d")
        date_line = f"today date: {today_date_str}\n"
        # Ensure there's no duplicate date line if called multiple times
        if resume_summary.startswith("today date:"):
             # Find the end of the existing date line and replace/update it
             first_newline = resume_summary.find('\n')
             if first_newline != -1:
                 return date_line + resume_summary[first_newline+1:]
             else: # Resume was only the date line? Unlikely but handle.
                 return date_line # Replace completely
        else:
             return f"{date_line}{resume_summary}"

    def update_resume_content(self, new_resume_content: str):
         """Updates the processor's resume content and its formatted version.
         
         The input should be plain text (already extracted from HTML if necessary).
         """
         if not isinstance(new_resume_content, str) or not new_resume_content:
              logger.error("Attempted to update resume with invalid content.")
              raise ValueError("New resume content must be a non-empty string.")
         
         self._raw_resume = new_resume_content
         self.formatted_resume = self._format_resume_with_date(self._raw_resume)
         logger.info("LLMProcessor resume content updated.")


    def set_current_job(self, job: Job):
        """
        Sets the job context for subsequent LLM tasks.

        Args:
            job (Job): The Job object representing the current job posting.

        Raises:
            TypeError: If the provided object is not a Job instance.
            ValueError: If the Job object is missing essential attributes.
        """
        if not isinstance(job, Job):
            raise TypeError(f"Expected a Job object, but received {type(job)}")

        # Validate essential job attributes needed for prompts
        missing_attrs = [attr for attr in ['title', 'company', 'location', 'description'] if not getattr(job, attr, None)]
        if missing_attrs:
            logger.error(f"Job object is missing essential attributes: {', '.join(missing_attrs)}")
            raise ValueError(f"Job object is missing essential attributes: {', '.join(missing_attrs)}")

        self.current_job = job
        logger.debug(f"Current job set to: {job.title} at {job.company}")


    def _create_prompt_template(self, template_string: str) -> ChatPromptTemplate:
        """
        Creates a LangChain ChatPromptTemplate from a preprocessed template string.

        Args:
            template_string (str): The raw template string.

        Returns:
            ChatPromptTemplate: The created prompt template instance.

        Raises:
            ValueError: If the template string is invalid.
        """
        processed_template = preprocess_template_string(template_string)
        if not processed_template:
             raise ValueError("Cannot create prompt template from empty string.")
        try:
            prompt = ChatPromptTemplate.from_template(processed_template)
            # logger.debug("ChatPromptTemplate created successfully.") # Can be verbose
            return prompt
        except Exception as e: # Catch potential errors from LangChain template creation
            logger.error(f"Error creating ChatPromptTemplate: {e}", exc_info=True)
            raise ValueError(f"Failed to create prompt template: {e}") from e


    def _execute_llm_call(self, prompt_template_str: str, context: Dict[str, Any]) -> str:
        """
        Helper method to format a prompt, invoke the LLM, and return the string content.

        Args:
            prompt_template_str (str): The raw string for the prompt template.
            context (Dict[str, Any]): Dictionary containing values to format the template.

        Returns:
            str: The content of the LLM response as a string.

        Raises:
            LLMInvocationError: If the LLM call fails.
            LLMParsingError: If the response cannot be parsed.
            ValueError: If template creation fails or context is invalid.
        """
        try:
            prompt_template = self._create_prompt_template(prompt_template_str)
            # Format the prompt using the provided context
            # LangChain's format_prompt().to_messages() or format() handles this
            # For simplicity, let's assume the wrapper's invoke handles formatted strings or message lists.
            # If the wrapper expects a specific format (e.g., message list), adjust here.
            # Example: formatted_input = prompt_template.format_prompt(**context).to_messages()
            # For now, assume invoke handles raw string from format:
            formatted_prompt = prompt_template.format(**context)
            logger.debug(f"Formatted prompt: {formatted_prompt[:200]}...") # Log start of prompt

        except (ValueError, KeyError) as e:
            logger.error(f"Error formatting prompt template: {e}. Context: {context.keys()}", exc_info=True)
            raise ValueError(f"Failed to format prompt: {e}") from e

        # Invoke the LLM via the wrapper
        # The wrapper handles logging, retries, and basic parsing.
        # It might return AIMessage or str.
        response = self.llm.invoke(formatted_prompt) # Pass the formatted prompt

        # Extract string content from the response
        if isinstance(response, AIMessage):
            return response.content
        elif isinstance(response, str):
            return response
        else:
            logger.error(f"LLM call returned unexpected type: {type(response)}. Returning empty string.")
            # Or raise an error depending on desired strictness
            # raise LLMParsingError(f"Unexpected response type from LLM wrapper: {type(response)}")
            return ""


    def answer_question_simple(self, question: str, character_limit: int = DEFAULT_ANSWER_CHAR_LIMIT) -> str:
        """
        Answers a simple question based on the current job context and resume.

        Args:
            question (str): The question to be answered.
            character_limit (int): The maximum character limit for the answer.

        Returns:
            str: The answer generated by the LLM, truncated if necessary.

        Raises:
            LLMError: If the LLM call fails or the job context is not set.
            ValueError: If the question is empty.
        """
        if not question:
            raise ValueError("Question cannot be empty.")
        if not self.current_job:
            raise LLMError("Job context not set. Call set_current_job() first.")

        logger.info(f"Answering simple question: '{question}' (Limit: {character_limit} chars)")

        # Adjust limit specifically for the 'headline' question
        effective_limit = (
            self.HEADLINE_CHAR_LIMIT if question.lower() == "headline"
            else character_limit or self.DEFAULT_ANSWER_CHAR_LIMIT
        )
        logger.debug(f"Using effective character limit: {effective_limit}")

        # Prepare context for the prompt template
        context = {
            "location": self.current_job.location,
            "limit_caractere": effective_limit, # Ensure template uses this name
            "job_title": self.current_job.title,
            "job_salary": self.current_job.salary or "Not Specified",
            "job_description": self.current_job.description,
            "resume": self.formatted_resume, # Use resume with current date
            "question": question,
        }

        try:
            # Use the appropriate template from prompt_strings
            template = prompt_strings.simple_question_template # Assuming template name
            answer = self._execute_llm_call(template, context)
            logger.debug(f"Raw answer for '{question}': {answer}")

            # Post-processing: Ensure within character limit and strip whitespace
            answer = answer.strip()
            if len(answer) > effective_limit:
                answer = answer[:effective_limit - 3] + "..." # Truncate nicely
                logger.debug(f"Answer truncated to {effective_limit} characters.")

            return answer

        except (LLMInvocationError, LLMParsingError, ValueError) as e:
            logger.error(f"Error answering simple question '{question}': {e}", exc_info=True)
            raise LLMError(f"Failed to answer simple question: {e}") from e
        except Exception as e: # Catch unexpected errors
            logger.critical(f"Unexpected error answering simple question '{question}': {e}", exc_info=True)
            raise LLMError(f"Unexpected error answering simple question: {e}") from e


    def answer_question_numeric(self, question: str) -> Optional[int]:
        """
        Answers a question expected to have a numeric answer, based on the resume.

        Args:
            question (str): The question seeking a numeric answer (e.g., "Years of experience?").

        Returns:
            Optional[int]: The extracted number, or None if not found or an error occurs.

        Raises:
            ValueError: If the question is empty.
            LLMError: For LLM or processing errors.
        """
        if not question:
            raise ValueError("Question cannot be empty.")

        logger.info(f"Answering numeric question: '{question}'")

        context = {
            "resume_summary": self.formatted_resume, # Use formatted resume
            "question": question,
        }

        try:
             # Assuming a template designed for numeric extraction exists
            template = prompt_strings.numeric_question_template
            raw_output = self._execute_llm_call(template, context)
            logger.debug(f"Raw output for numeric question '{question}': {raw_output}")

            # Extract the number using the utility function
            extracted_number = extract_number_from_string(raw_output)

            if extracted_number is None:
                logger.warning(f"Could not extract a number for question: '{question}' from output: '{raw_output}'")
                return None # Return None if no number found

            logger.info(f"Extracted number {extracted_number} for question: '{question}'")
            return extracted_number

        except (LLMInvocationError, LLMParsingError, ValueError) as e:
            logger.error(f"Error answering numeric question '{question}': {e}", exc_info=True)
            # Decide whether to raise or return None. Returning None for now.
            return None
        except Exception as e:
            logger.critical(f"Unexpected error answering numeric question '{question}': {e}", exc_info=True)
            return None


    def answer_question_from_options(self, question: str, options: List[str]) -> Optional[str]:
        """
        Selects the best option from a list to answer a question, based on the resume.

        Args:
            question (str): The question to answer.
            options (List[str]): A list of possible answer choices.

        Returns:
            Optional[str]: The best matching option string, or None if no suitable match found or error occurs.

        Raises:
            ValueError: If the question or options are invalid.
            LLMError: For LLM or processing errors.
        """
        if not question:
            raise ValueError("Question cannot be empty.")
        if not options or not isinstance(options, list) or not all(isinstance(opt, str) for opt in options):
            raise ValueError("Options must be a non-empty list of strings.")

        logger.info(f"Answering question from options: '{question}'")
        logger.debug(f"Available options: {options}")

        options_str = ", ".join(f"'{opt}'" for opt in options) # Format for prompt clarity
        context = {
            "resume": self.formatted_resume, # Use formatted resume
            "question": question,
            "options": options_str,
        }

        try:
            template = prompt_strings.options_template # Assuming template name
            llm_suggestion = self._execute_llm_call(template, context)
            logger.debug(f"LLM suggested answer for '{question}': '{llm_suggestion}'")

            # Find the best match from the original options list using Levenshtein distance
            best_match = find_best_match(llm_suggestion, options)

            if best_match is None:
                 logger.warning(f"Could not find a suitable match for LLM suggestion '{llm_suggestion}' in options: {options}")
                 return None # Return None if no good match

            logger.info(f"Selected option '{best_match}' for question: '{question}'")
            return best_match

        except (LLMInvocationError, LLMParsingError, ValueError, TypeError) as e: # Added TypeError for find_best_match
            logger.error(f"Error answering question from options '{question}': {e}", exc_info=True)
            return None # Return None on error
        except Exception as e:
            logger.critical(f"Unexpected error answering question from options '{question}': {e}", exc_info=True)
            return None


    def answer_question_date(self, question: str) -> Optional[datetime]:
        """
        Generates an appropriate date based on a question using the LLM.

        Args:
            question (str): The question related to a date (e.g., "Start date?").

        Returns:
            Optional[datetime]: A datetime object representing the generated date, or None on failure.

        Raises:
            ValueError: If the question is empty.
            LLMError: For LLM or processing errors.
        """
        if not question:
            raise ValueError("Question cannot be empty.")

        logger.info(f"Answering date question: '{question}'")
        today_date_str = format_datetime(datetime.now(), "%Y-%m-%d")

        context = {
            "question": question,
            "today_date": today_date_str,
            "resume": self.formatted_resume, # Include resume for context if needed by template
            # Add job context if relevant?
            # "job_title": self.current_job.title if self.current_job else "N/A",
            # "job_description": self.current_job.description if self.current_job else "N/A",
        }

        try:
            template = prompt_strings.date_question_template # Assuming template name
            date_str_output = self._execute_llm_call(template, context)
            logger.debug(f"Raw date output for '{question}': {date_str_output}")

            # Attempt to parse the date string (expecting YYYY-MM-DD format from template)
            date_str = date_str_output.strip()
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
            logger.info(f"Parsed date {format_datetime(parsed_date, '%Y-%m-%d')} for question: '{question}'")
            return parsed_date

        except ValueError as ve: # Catch parsing errors specifically
            logger.error(f"Failed to parse date string '{date_str_output}' from LLM: {ve}")
            return None # Return None if parsing fails
        except (LLMInvocationError, LLMParsingError) as e:
            logger.error(f"LLM error answering date question '{question}': {e}", exc_info=True)
            return None
        except Exception as e:
            logger.critical(f"Unexpected error answering date question '{question}': {e}", exc_info=True)
            return None

    def evaluate_job_fit(self) -> float:
        """
        Evaluates the compatibility score (0-10) between the current job and the resume.

        Returns:
            float: A score from 0.0 to 10.0 representing compatibility. Returns 0.1 on error.

        Raises:
            LLMError: If the job context is not set.
        """
        if not self.current_job:
            raise LLMError("Job context not set. Call set_current_job() first.")

        logger.debug(f"Evaluating job fit for: {self.current_job.title}")

        context = {
            "location": self.current_job.location,
            "job_title": self.current_job.title,
            "job_salary": self.current_job.salary or "Not Specified",
            "job_description": self.current_job.description,
            "resume_summary": self.formatted_resume, # Use formatted resume
        }

        try:
            template = prompt_strings.evaluate_job_template # Assuming template name
            response = self._execute_llm_call(template, context)
            logger.debug(f"Raw evaluation score response: {response}")

            # Enhanced score extraction: find float or int, handle ranges maybe
            match = re.search(r"\b(\d+(\.\d+)?)\b", response) # Find first number (int or float)
            if match:
                score = float(match.group(1))
                # Clamp score between 0 and 10
                score = max(0.0, min(10.0, score))
                logger.debug(f"Extracted job fit score: {score:.2f}")
                return round(score, 2)
            else:
                logger.warning(f"Could not extract a valid score from response: '{response}'. Returning default low score.")
                return 0.1 # Default low score if extraction fails

        except (LLMInvocationError, LLMParsingError, ValueError) as e:
            logger.error(f"Error evaluating job fit: {e}", exc_info=True)
            return 0.1 # Return default low score on error
        except Exception as e:
            logger.critical(f"Unexpected error evaluating job fit: {e}", exc_info=True)
            return 0.1


    def estimate_salary(self) -> float:
        """
        Estimates the likely annual salary for the candidate for the current job.

        Returns:
            float: The estimated annual salary in USD. Returns 0.1 on error.

        Raises:
            LLMError: If the job context is not set.
        """
        if not self.current_job:
            raise LLMError("Job context not set. Call set_current_job() first.")

        logger.info(f"Estimating salary for: {self.current_job.title}")

        # Include salary expectation in the resume context for the prompt
        salary_expectation_line = f"Candidate's desired salary (USD annual): {self.salary_expectations}\n"
        resume_with_salary = f"{salary_expectation_line}{self.formatted_resume}"

        context = {
            "location": self.current_job.location,
            "job_title": self.current_job.title,
            "job_salary": self.current_job.salary or "Not Specified", # Salary mentioned in JD
            "job_description": self.current_job.description,
            "resume_summary": resume_with_salary, # Use resume including salary expectation
        }

        try:
            template = prompt_strings.estimate_salary_template # Assuming template name
            response = self._execute_llm_call(template, context)
            logger.debug(f"Raw salary estimation response: {response}")

            # Extract number - more robustly handle currency symbols, commas, ranges
            # Remove common currency symbols and commas
            cleaned_response = re.sub(r"[$,]", "", response)
             # Look for numbers, potentially separated by 'to' or '-' for ranges
            numbers = re.findall(r"\b\d+(?:\.\d+)?\b", cleaned_response) # Find potential numbers

            if not numbers:
                 logger.warning(f"Could not extract any numeric value from salary estimation: '{response}'. Returning default.")
                 return 0.1

            # If multiple numbers found (likely a range), take the highest
            float_numbers = [float(n) for n in numbers]
            estimated_salary = max(float_numbers)

            # Basic sanity check (e.g., salary > 1000?)
            if estimated_salary < 1000:
                 logger.warning(f"Extracted salary {estimated_salary} seems unusually low. Check LLM response or prompt.")
                 # Return default or the low value depending on desired behavior
                 return 0.1 # Default low value

            logger.info(f"Estimated salary: {estimated_salary:.2f} USD")
            return round(estimated_salary, 2)

        except (LLMInvocationError, LLMParsingError, ValueError) as e:
            logger.error(f"Error estimating salary: {e}", exc_info=True)
            return 0.1 # Return default low value on error
        except Exception as e:
            logger.critical(f"Unexpected error estimating salary: {e}", exc_info=True)
            return 0.1

    def extract_keywords_from_job_description(self) -> List[str]:
        """
        Extracts key terms from the current job's description using the LLM.

        Returns:
            List[str]: A list of extracted keywords. Returns empty list on error.

        Raises:
            LLMError: If the job context is not set.
        """
        if not self.current_job or not self.current_job.description:
            raise LLMError("Job context or description not set. Call set_current_job() first.")

        logger.info("Extracting keywords from job description...")

        context = {"job_description": self.current_job.description}

        try:
            template = prompt_strings.extract_keywords_template # Assuming template name
            response = self._execute_llm_call(template, context)
            logger.debug(f"Raw keyword extraction response: {response}")

            # Attempt to parse the response as a JSON list (as requested by the template)
            try:
                 # Be robust: find the JSON list within potential surrounding text
                match = re.search(r'\[.*?\]', response, re.DOTALL)
                if match:
                    keywords_str = match.group(0)
                    keywords = json.loads(keywords_str)
                    if isinstance(keywords, list) and all(isinstance(kw, str) for kw in keywords):
                        logger.info(f"Successfully extracted {len(keywords)} keywords.")
                        return keywords
                    else:
                         logger.warning(f"Parsed JSON is not a list of strings: {keywords_str}")
                else:
                     logger.warning(f"Could not find a JSON list in the keyword response: '{response}'")

            except json.JSONDecodeError as json_err:
                logger.warning(f"Failed to parse keyword response as JSON: {json_err}. Falling back to regex extraction.")
                # Fallback: Extract quoted strings or comma-separated values if JSON fails
                keywords = re.findall(r"['\"]([^'\"]+)['\"]", response) # Find words in quotes
                if not keywords:
                     keywords = [kw.strip() for kw in response.split(',') if kw.strip()] # Split by comma
                if keywords:
                     logger.info(f"Extracted {len(keywords)} keywords using fallback method.")
                     return keywords

            logger.warning("Failed to extract keywords using primary and fallback methods.")
            return [] # Return empty list if extraction fails

        except (LLMInvocationError, LLMParsingError, ValueError) as e:
            logger.error(f"Error extracting keywords: {e}", exc_info=True)
            return [] # Return empty list on error
        except Exception as e:
            logger.critical(f"Unexpected error extracting keywords: {e}", exc_info=True)
            return []

    def generate_tailored_summary(self, keywords: List[str]) -> str:
        """
        Generates a resume summary tailored to the provided keywords and current job.

        Args:
            keywords (List[str]): Keywords extracted from the job description.

        Returns:
            str: The generated tailored summary, or the original formatted resume on error.

        Raises:
            LLMError: If the job context is not set.
            ValueError: If the keywords list is empty.
        """
        if not self.current_job:
            raise LLMError("Job context not set. Call set_current_job() first.")
        if not keywords:
             # Decide behavior: raise error or use original summary?
             logger.warning("Keywords list is empty. Cannot generate tailored summary. Returning original.")
             # raise ValueError("Keywords list cannot be empty for generating tailored summary.")
             return self.formatted_resume # Return original as fallback

        logger.info("Generating tailored resume summary based on keywords...")
        keywords_str = ', '.join(keywords)

        context = {
            "resume_summary": self._raw_resume, # Provide the original base resume for context
            "resume": self.formatted_resume, # Provide formatted one too if template needs date etc.
            "keywords_str": keywords_str,
             # Add job context if template requires it
            "job_title": self.current_job.title,
            "job_description": self.current_job.description,
        }

        try:
            template = prompt_strings.tailored_summary_template # Assuming template name
            tailored_summary = self._execute_llm_call(template, context)
            logger.info("Tailored summary generated successfully.")
            logger.debug(f"Tailored Summary: {tailored_summary[:200]}...")

            # Add date back to the tailored summary if needed downstream
            # return self._format_resume_with_date(tailored_summary.strip())
            return tailored_summary.strip() # Return without date for direct use?

        except (LLMInvocationError, LLMParsingError, ValueError) as e:
            logger.error(f"Error generating tailored summary: {e}", exc_info=True)
            return self.formatted_resume # Return original formatted resume on error
        except Exception as e:
            logger.critical(f"Unexpected error generating tailored summary: {e}", exc_info=True)
            return self.formatted_resume

    def generate_cover_letter(self, keywords: List[str]) -> str:
        """
        Generates a cover letter tailored to the current job and keywords.

        Args:
            keywords (List[str]): Keywords extracted from the job description.

        Returns:
            str: The generated cover letter content, or an empty string on error.

        Raises:
            LLMError: If the job context is not set.
        """
        if not self.current_job:
            raise LLMError("Job context not set. Call set_current_job() first.")
        # Allow empty keywords? Cover letter might still be possible.
        # if not keywords:
        #     raise ValueError("Keywords list cannot be empty for generating cover letter.")

        logger.info("Generating tailored cover letter...")
        keywords_str = ', '.join(keywords) if keywords else "Not available"

        context = {
            "job_description": self.current_job.description,
            "resume": self.formatted_resume, # Use resume with date
            "keywords_str": keywords_str,
             # Add more context if needed (company name, job title explicitly)
            "job_title": self.current_job.title,
            "company_name": self.current_job.company,
        }

        try:
            template = prompt_strings.cover_letter_template # Assuming template name
            cover_letter = self._execute_llm_call(template, context)
            logger.info("Cover letter generated successfully.")
            logger.debug(f"Generated Cover Letter: {cover_letter[:200]}...")
            return cover_letter.strip()

        except (LLMInvocationError, LLMParsingError, ValueError) as e:
            logger.error(f"Error generating cover letter: {e}", exc_info=True)
            return "" # Return empty string on error
        except Exception as e:
            logger.critical(f"Unexpected error generating cover letter: {e}", exc_info=True)
            return ""

    def check_resume_or_cover(self, phrase: str) -> str:
        """
        Determines if a phrase likely refers to 'resume' or 'cover letter'.

        Args:
            phrase (str): The input phrase (e.g., a button label "Upload Resume").

        Returns:
            str: Either 'resume' or 'cover'. Defaults to 'resume' if unsure or on error.

        Raises:
            ValueError: If the phrase is empty.
        """
        if not phrase:
            raise ValueError("Phrase cannot be empty.")

        logger.info(f"Checking phrase for 'resume' or 'cover': '{phrase}'")

        # Simple heuristic check first to potentially avoid LLM call
        phrase_lower = phrase.lower()
        if "resume" in phrase_lower or "cv" in phrase_lower or "curriculum" in phrase_lower:
             logger.debug("Heuristic match found: 'resume'")
             return "resume"
        if "cover" in phrase_lower or "letter" in phrase_lower:
             # Check if it *also* contains resume, e.g. "Upload Resume and Cover Letter"
             if "resume" not in phrase_lower and "cv" not in phrase_lower:
                  logger.debug("Heuristic match found: 'cover'")
                  return "cover"
             # If both are present, maybe default to resume or let LLM decide? Defaulting to resume for now.
             logger.debug("Heuristic match found both 'resume' and 'cover'. Defaulting to 'resume'.")
             return "resume"
        # Handle ambiguous cases like just "Upload" - often implies cover letter if resume was separate
        if phrase_lower == "upload":
             logger.debug("Heuristic match for 'upload': defaulting to 'cover'")
             return "cover"


        # If heuristic is unclear, use LLM (this might be overkill often)
        logger.debug("Heuristic unclear, using LLM to determine resume/cover.")
        context = {"phrase": phrase}

        try:
            template = prompt_strings.resume_or_cover_template # Assuming template name
            response = self._execute_llm_call(template, context)
            logger.debug(f"LLM response for resume/cover check: '{response}'")

            response_lower = response.lower().strip()
            if "resume" in response_lower:
                return "resume"
            elif "cover" in response_lower:
                return "cover"
            else:
                logger.warning(f"LLM response '{response}' unclear for resume/cover check. Defaulting to 'resume'.")
                return "resume" # Default if LLM is ambiguous

        except (LLMInvocationError, LLMParsingError, ValueError) as e:
            logger.error(f"LLM error checking resume/cover phrase '{phrase}': {e}", exc_info=True)
            return "resume" # Default to resume on error
        except Exception as e:
            logger.critical(f"Unexpected error checking resume/cover phrase '{phrase}': {e}", exc_info=True)
            return "resume"
