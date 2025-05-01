# src/easy_apply/answer_storage.py
"""
Handles the storage and retrieval of previously used answers for form fields,
typically stored in a JSON file.
"""
import json
import re
from pathlib import Path
from typing import List, Optional, Dict, Any
from loguru import logger

# Default path relative to project root or data folder - consider making configurable
DEFAULT_ANSWERS_FILENAME = "answers.json"
DEFAULT_OUTPUT_DIR = Path("data_folder/output") # Example default

class AnswerStorage:
    """
    Manages storing and retrieving answers to previously encountered form questions
    to speed up form filling. Answers are stored in a JSON file.
    """

    def __init__(self, output_dir: Path = DEFAULT_OUTPUT_DIR):
        """
        Initializes the AnswerStorage.

        Args:
            output_dir (Path): The directory where the answers JSON file resides or will be created.
                               Defaults to DEFAULT_OUTPUT_DIR.
        """
        if not isinstance(output_dir, Path):
             output_dir = Path(output_dir) # Ensure it's a Path object

        self.output_dir: Path = output_dir
        self.output_file: Path = self.output_dir / DEFAULT_ANSWERS_FILENAME
        self.all_questions: List[Dict[str, Any]] = [] # Initialize empty

        try:
             # Ensure directory exists during initialization
             self.output_dir.mkdir(parents=True, exist_ok=True)
             self.all_questions = self._load_questions_from_json() # Load existing answers
             logger.info(f"AnswerStorage initialized. Loaded {len(self.all_questions)} answers from {self.output_file}")
        except Exception as e:
             logger.error(f"Failed to initialize AnswerStorage or load answers from {self.output_file}: {e}", exc_info=True)
             # Continue with empty list, but log error
             self.all_questions = []


    def sanitize_text(self, text: Optional[str]) -> str:
        """
        Sanitizes question or answer text for consistent matching and storage.
        Lowers case, strips whitespace, removes certain problematic characters.

        Args:
            text (Optional[str]): The text to sanitize.

        Returns:
            str: The sanitized text, or an empty string if input is None.
        """
        if text is None:
            return ""
        # Lowercase and strip whitespace
        sanitized = text.lower().strip()
        # Replace quotes, backslashes, newlines, carriage returns with spaces
        sanitized = re.sub(r'["\\\n\r]', ' ', sanitized)
        # Remove trailing commas (often seen in scraped labels)
        sanitized = sanitized.rstrip(",")
        # Remove control characters and DEL
        sanitized = re.sub(r"[\x00-\x1F\x7F]", "", sanitized)
        # Normalize multiple whitespace characters to a single space
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        return sanitized

    def save_question(self, question_data: Dict[str, Any]) -> None:
        """
        Saves a new question-answer pair to the JSON file if the question doesn't already exist.

        Args:
            question_data (Dict[str, Any]): Dictionary containing 'type', 'question', and 'answer'.
                                           The 'question' will be sanitized before checking/saving.
        """
        if not all(k in question_data for k in ["type", "question", "answer"]):
            logger.warning(f"Attempted to save incomplete question data: {question_data}. Skipping.")
            return

        original_question = question_data.get("question", "")
        sanitized_question = self.sanitize_text(original_question)

        # Ensure sanitized question is not empty
        if not sanitized_question:
             logger.warning(f"Skipping save for question with empty sanitized text. Original: '{original_question}'")
             return

        # Overwrite original question with sanitized version for storage consistency
        question_data["question"] = sanitized_question
        logger.debug(f"Attempting to save sanitized question: '{sanitized_question}' Type: '{question_data.get('type')}'")

        try:
            # Check if question already exists in memory cache (more efficient)
            if any(self.sanitize_text(item.get("question")) == sanitized_question for item in self.all_questions):
                logger.trace(f"Question already exists in memory cache, not saving again: '{sanitized_question}'")
                return

            # If not in memory, load file data again (in case of external changes, though less likely)
            # and add the new entry. This ensures persistence even if in-memory check fails somehow.
            current_data = self._load_questions_from_json(log_on_error=False) # Load quietly

            # Double-check file data for duplicates before appending
            if any(self.sanitize_text(item.get("question")) == sanitized_question for item in current_data):
                 logger.trace(f"Question already exists in file, not saving again: '{sanitized_question}'")
                 # Add to in-memory cache if it wasn't there for some reason
                 if not any(self.sanitize_text(item.get("question")) == sanitized_question for item in self.all_questions):
                      self.all_questions.append(question_data)
                 return

            # Add the new question to list
            current_data.append(question_data)

            # Write the updated list back to the file
            with self.output_file.open("w", encoding="utf-8") as f:
                json.dump(current_data, f, indent=4, ensure_ascii=False)

            # Update the in-memory cache as well
            self.all_questions.append(question_data)

            logger.debug(f"Question saved successfully: '{sanitized_question}'")

        except Exception as e:
            # Log error but don't crash the application over a failed answer save
            logger.error(f"Error saving question data to {self.output_file}: {e}", exc_info=True)


    def _load_questions_from_json(self, log_on_error: bool = True) -> List[Dict[str, Any]]:
        """
        Loads previously answered questions from the JSON file.

        Args:
            log_on_error (bool): Whether to log errors if loading fails (used internally to avoid recursion).

        Returns:
            List[Dict[str, Any]]: A list of valid question data dictionaries found in the file.
        """
        logger.trace(f"Loading questions from JSON file: {self.output_file}")
        valid_data: List[Dict[str, Any]] = []
        try:
            if not self.output_file.exists():
                if log_on_error: logger.warning(f"Answers file not found: {self.output_file}. Returning empty list.")
                return [] # Return empty list, don't create file here

            with self.output_file.open("r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    logger.debug("Answers file is empty. Returning empty list.")
                    return []

                try:
                    data = json.loads(content)
                except json.JSONDecodeError as json_err:
                     if log_on_error: logger.error(f"Failed to decode JSON from {self.output_file}: {json_err}. Returning empty list.")
                     return [] # Return empty on decode error

                if not isinstance(data, list):
                     if log_on_error: logger.error(f"Invalid format in {self.output_file}. Expected a JSON list, found {type(data)}. Returning empty list.")
                     return []

                # Validate items in the loaded list
                for i, item in enumerate(data):
                    if isinstance(item, dict) and all(k in item for k in ["type", "question", "answer"]):
                        # Sanitize question during load for consistency? Or keep original? Let's sanitize.
                        item["question"] = self.sanitize_text(item.get("question"))
                        if item["question"]: # Only add if sanitized question is not empty
                             valid_data.append(item)
                        elif log_on_error:
                             logger.warning(f"Loaded item {i} has empty sanitized question. Skipping.")
                    elif log_on_error:
                        logger.warning(f"Invalid item format found in {self.output_file} at index {i}: {item}. Skipping.")

                logger.trace(f"Loaded {len(valid_data)} valid questions from JSON.")
                return valid_data

        except IOError as io_err:
             if log_on_error: logger.error(f"IOError reading answers file {self.output_file}: {io_err}", exc_info=True)
             return [] # Return empty on IO error
        except Exception as e:
            if log_on_error: logger.error(f"Unexpected error loading question data from {self.output_file}: {e}", exc_info=True)
            return [] # Return empty on other errors

    def get_existing_answer(self, question_text: str, question_type: str) -> Optional[str]:
        """
        Retrieves an existing answer for a question based on sanitized text and type match.

        Args:
            question_text (str): The question text asked in the form.
            question_type (str): The type of form field (e.g., 'radio', 'dropdown', 'text').

        Returns:
            Optional[str]: The stored answer string if found, otherwise None.
        """
        sanitized_question_to_find = self.sanitize_text(question_text)
        if not sanitized_question_to_find:
             logger.warning("Attempted to find answer for an empty sanitized question.")
             return None

        logger.debug(f"Searching for answer to: '{sanitized_question_to_find}' (Type: {question_type})")
        try:
            # Search in the in-memory cache
            for item in self.all_questions:
                # Item question should already be sanitized if loaded/saved correctly
                item_question = item.get("question", "")
                item_type = item.get("type")

                # Match sanitized question and type
                if item_question == sanitized_question_to_find and item_type == question_type:
                    answer = item.get("answer") # Answer itself is stored as originally provided
                    logger.info(f"Found existing answer for '{sanitized_question_to_find}': '{answer}'")
                    return answer # Return the stored answer (not sanitized)

            logger.debug(f"No existing answer found for: '{sanitized_question_to_find}' (Type: {question_type})")
            return None
        except Exception as e:
             # Should not happen if all_questions contains valid dicts, but good safeguard
             logger.error(f"Unexpected error searching for answer to '{sanitized_question_to_find}': {e}", exc_info=True)
             return None