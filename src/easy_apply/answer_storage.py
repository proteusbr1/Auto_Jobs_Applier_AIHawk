"""
Module for storing and retrieving form answers in JSON format.
"""
import json
import re
from pathlib import Path
from typing import List, Optional, Dict, Any
from loguru import logger

class AnswerStorage:
    """
    Handles the storage and retrieval of form answers in JSON format.
    """
    
    def __init__(self, output_dir: str = "data_folder/output"):
        """
        Initialize the AnswerStorage with the specified output directory.
        
        Args:
            output_dir (str): The directory where the answers JSON file will be stored.
        """
        self.output_dir = Path(output_dir)
        self.output_file = self.output_dir / "answers.json"
        self.all_questions = self._load_questions_from_json()
        
    def sanitize_text(self, text: str) -> str:
        """
        Sanitizes the input text by lowering case, stripping whitespace, and removing unwanted characters.
        
        Args:
            text (str): The text to sanitize.
            
        Returns:
            str: The sanitized text.
        """
        sanitized_text = text.lower().strip()
        sanitized_text = re.sub(r'[\"\\\n\r]', ' ', sanitized_text)
        sanitized_text = sanitized_text.rstrip(",")
        sanitized_text = re.sub(r"[\x00-\x1F\x7F]", "", sanitized_text)
        sanitized_text = re.sub(r'\s+', ' ', sanitized_text)
        return sanitized_text
    
    def save_question(self, question_data: Dict[str, Any]) -> None:
        """
        Saves the question and answer to a JSON file for future reuse only if the question is not a duplicate.
        
        Args:
            question_data (Dict[str, Any]): The question data to save, containing 'type', 'question', and 'answer'.
        """
        sanitized_question = self.sanitize_text(question_data["question"])
        question_data["question"] = sanitized_question
        logger.debug(f"Attempting to save question data to JSON: {question_data}")
        
        try:
            # Ensure the directory exists
            self.output_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Directory verified or created: {self.output_dir}")
            
            if self.output_file.exists():
                with self.output_file.open("r", encoding="utf-8") as f:
                    try:
                        data = json.load(f)
                        if not isinstance(data, list):
                            logger.error("The JSON file format is incorrect. Expected a list of questions.")
                            raise ValueError("The JSON file format is incorrect. Expected a list of questions.")
                    except json.JSONDecodeError:
                        logger.warning("JSON file is empty or invalid. Initializing with an empty list.")
                        data = []
            else:
                data = []
                logger.info(f"JSON file not found. Creating new file: {self.output_file}")
            
            # Check if the question already exists
            if any(self.sanitize_text(item["question"]) == sanitized_question for item in data):
                logger.debug(f"Question already exists and will not be saved again: {sanitized_question}")
                return  # Do not save duplicates
            
            # Add the new question
            data.append(question_data)
            
            with self.output_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            # Update the in-memory cache
            self.all_questions.append(question_data)
            
            logger.debug("Question data successfully saved to JSON")
        
        except Exception as e:
            logger.error("Error saving question data to JSON file", exc_info=True)
            raise
    
    def _load_questions_from_json(self) -> List[Dict[str, Any]]:
        """
        Loads previously answered questions from a JSON file to reuse answers.
        
        Returns:
            List[Dict[str, Any]]: A list of question data dictionaries.
        """
        logger.debug(f"Loading questions from JSON file: {self.output_file}")
        try:
            if not self.output_file.exists():
                logger.warning(f"JSON file not found: {self.output_file}. Creating an empty file.")
                # Ensure the directory exists
                self.output_file.parent.mkdir(parents=True, exist_ok=True)
                # Create the file with an empty list
                with self.output_file.open("w", encoding="utf-8") as f:
                    json.dump([], f, indent=4, ensure_ascii=False)
                return []
            
            with self.output_file.open("r", encoding="utf-8") as f:
                try:
                    content = f.read().strip()
                    if not content:
                        logger.debug("JSON file is empty. Returning an empty list.")
                        return []
                    data = json.loads(content)
                    if not isinstance(data, list):
                        logger.error("The JSON file format is incorrect. Expected a list of questions.")
                        raise ValueError("The JSON file format is incorrect. Expected a list of questions.")
                except json.JSONDecodeError:
                    logger.warning("JSON decoding failed. Returning an empty list.")
                    return []
            
            logger.debug("Questions successfully loaded from JSON")
            logger.debug("Validating loaded questions...")
            valid_data = []
            for item in data:
                if isinstance(item, dict) and all(k in item for k in ["type", "question", "answer"]):
                    valid_data.append(item)
                else:
                    logger.error(f"Invalid item in answers.json: {item}")
            logger.debug(f"Total of {len(valid_data)} valid questions loaded.")
            return valid_data
        except Exception as e:
            logger.error("Error loading question data from JSON file", exc_info=True)
            raise
    
    def get_existing_answer(self, question_text: str, question_type: str) -> Optional[str]:
        """
        Retrieves an existing answer for a question if it exists.
        
        Args:
            question_text (str): The question text to look for.
            question_type (str): The type of question (e.g., 'radio', 'dropdown', 'textbox').
            
        Returns:
            Optional[str]: The answer if found, None otherwise.
        """
        sanitized_question = self.sanitize_text(question_text)
        try:
            for item in self.all_questions:
                if not isinstance(item, dict):
                    logger.error(f"Unexpected item type in all_questions: {type(item)} - {item}")
                    continue
                item_question = self.sanitize_text(item.get("question", ""))
                item_type = item.get("type")
                logger.debug(f"Checking item: question='{item_question}', type='{item_type}'")
                if item_question == sanitized_question and item_type == question_type:
                    return item.get("answer")
            return None
        except KeyError as e:
            logger.error(f"KeyError when accessing item in all_questions: {e}", exc_info=True)
            return None
