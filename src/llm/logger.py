"""
Logger classes for logging AI model interactions.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Union

import httpx
from langchain_core.messages import BaseMessage
from langchain_core.messages.ai import AIMessage
from langchain_core.prompt_values import StringPromptValue, ChatPromptValue

from loguru import logger
from src.llm.utils import MODEL_PRICING
from src.llm.models import AIModel


class LLMLogger:
    """
    Logger class for logging AI model interactions.
    """

    def __init__(self, llm: AIModel):
        """
        Initialize the LLMLogger with the given AI model.

        Args:
            llm (AIModel): The AI model instance.
        """
        self.llm = llm
        logger.debug(f"LLMLogger initialized with LLM: {self.llm}")
        self.model_name = self._get_model_name()

    def _get_model_name(self) -> str:
        """
        Retrieve the model name from the LLM instance.

        Returns:
            str: The name of the model.
        """
        try:
            model_name = self.llm.model.model_name  # Ajuste conforme a estrutura do objeto LLM
            logger.debug(f"Detected model name: {model_name}")
            return model_name
        except AttributeError:
            logger.error("Unable to retrieve the model name from the LLM instance.")
            return "unknown_model"

    @staticmethod
    def log_request(prompts: Union[List[BaseMessage], StringPromptValue, Dict], parsed_reply: Dict[str, Dict], model_name: str):
        """
        Log the details of an AI model request and its response.

        Args:
            prompts (Union[List[BaseMessage], StringPromptValue, Dict]): The prompts sent to the AI model.
            parsed_reply (Dict[str, Dict]): The parsed response from the AI model.
            model_name (str): The name of the AI model used.

        Raises:
            Exception: If an error occurs during logging.
        """
        logger.debug("Starting log_request method.")
        logger.debug(f"Prompts received: {prompts}")
        logger.debug(f"Parsed reply received: {parsed_reply}")
        logger.debug(f"Model used: {model_name}")

        if isinstance(prompts, ChatPromptValue):
            logger.debug("Prompts are of type ChatPromptValue.")
            # Access 'messages' attribute if available
            prompts = prompts.messages if hasattr(prompts, 'messages') else prompts.text
            logger.debug(f"Prompts converted to text/messages: {prompts}")

        try:
            calls_log = os.path.join(Path("data_folder/output"), "open_ai_calls.json")
            logger.debug(f"Logging path determined: {calls_log}")
        except Exception as e:
            logger.error(f"Error determining the log path: {e}")
            raise

        if isinstance(prompts, StringPromptValue):
            logger.debug("Prompts are of type StringPromptValue.")
            prompts = prompts.text
            logger.debug(f"Prompts converted to text: {prompts}")
        elif isinstance(prompts, Dict):
            logger.debug("Prompts are of type Dict.")
            try:
                # Handle both dict and object with 'content' attribute
                prompts = {f"prompt_{i + 1}": (prompt.get('content') if isinstance(prompt, dict) else prompt.content)
                          for i, prompt in enumerate(prompts.get('messages', []))}
                logger.debug(f"Prompts converted to dictionary: {prompts}")
            except Exception as e:
                logger.error(f"Error converting prompts to dictionary: {e}")
                raise
        elif isinstance(prompts, list):
            logger.debug("Prompts are of type list.")
            try:
                prompts = {f"prompt_{i + 1}": (prompt.get('content') if isinstance(prompt, dict) else prompt.content)
                          for i, prompt in enumerate(prompts)}
                logger.debug(f"Prompts converted to dictionary: {prompts}")
            except Exception as e:
                logger.error(f"Error converting prompts from list to dictionary: {e}")
                raise
        else:
            logger.debug("Prompts are of unknown type, attempting default conversion.")
            try:
                prompts = {f"prompt_{i + 1}": (prompt.get('content') if isinstance(prompt, dict) else prompt.content)
                          for i, prompt in enumerate(prompts.get('messages', []))}
                logger.debug(f"Prompts converted to dictionary using default method: {prompts}")
            except Exception as e:
                logger.error(f"Error converting prompts using default method: {e}")
                raise

        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.debug(f"Current time obtained: {current_time}")
        except Exception as e:
            logger.error(f"Error obtaining current time: {e}")
            raise

        try:
            token_usage = parsed_reply.get("usage_metadata", {})
            output_tokens = token_usage.get("output_tokens", 0)
            input_tokens = token_usage.get("input_tokens", 0)
            total_tokens = token_usage.get("total_tokens", 0)
            logger.debug(f"Token usage - Input: {input_tokens}, Output: {output_tokens}, Total: {total_tokens}")
        except AttributeError as e:
            logger.error(f"AttributeError in parsed_reply structure: {e}")
            raise

        try:
            response_metadata = parsed_reply.get("response_metadata", {})
            model_name = response_metadata.get("model_name", "unknown_model")
            logger.debug(f"Model name from response_metadata: {model_name}")
        except AttributeError as e:
            logger.error(f"AttributeError in response_metadata: {e}")
            raise

        pricing = MODEL_PRICING.get(model_name.lower(), None)
        if pricing is None:
            logger.warning(f"Prices not defined for model '{model_name}'. Using default prices.")
            prompt_price_per_token = 0.00000015  # Default price
            completion_price_per_token = 0.0000006  # Default price
        else:
            prompt_price_per_token = pricing["input_token_price"]
            completion_price_per_token = pricing["output_token_price"]
            logger.debug(f"Applying prices for model '{model_name}': "
                        f"Input Token: {prompt_price_per_token}, Output Token: {completion_price_per_token}")
            
        try:
            total_cost = (input_tokens * prompt_price_per_token) + (output_tokens * completion_price_per_token)
            logger.debug(f"Total cost calculated: {total_cost}")
        except Exception as e:
            logger.error(f"Error calculating total cost: {e}")
            raise

        try:
            log_entry = {
                "model": model_name,
                "time": current_time,
                "prompts": prompts,
                "replies": parsed_reply.get("content", ""),
                "total_tokens": total_tokens,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_cost": total_cost,
            }
            logger.debug(f"Log entry created: {log_entry}")
        except KeyError as e:
            logger.error(f"KeyError while creating log entry: {e}")
            raise

        try:
            with open(calls_log, "a", encoding="utf-8") as f:
                json_string = json.dumps(log_entry, ensure_ascii=False, indent=4)
                f.write(json_string + "\n")
                logger.debug(f"Log entry written to file: {calls_log}")
        except Exception as e:
            logger.error(f"Error writing log entry to file: {e}")
            raise


class LoggerChatModel:
    """
    Chat model wrapper that logs interactions with the AI model.
    """

    def __init__(self, llm: AIModel):
        """
        Initialize the LoggerChatModel with the given AI model.

        Args:
            llm (AIModel): The AI model instance.
        """
        self.llm = llm
        logger.debug(f"LoggerChatModel initialized with LLM: {self.llm}")

    def __call__(self, messages: List[Dict[str, str]]) -> AIMessage:
        """
        Make the LoggerChatModel callable. It handles invoking the AI model,
        parsing the response, and logging the interaction.

        Args:
            messages (List[Dict[str, str]]): The list of messages to send to the AI model.

        Returns:
            AIMessage: The response from the AI model.

        Raises:
            ValueError: If the response format is unexpected.
            Exception: For any other errors during invocation or logging.
        """
        logger.debug(f"Entering __call__ method with messages: {messages}")
        while True:
            try:
                logger.debug("Attempting to call the LLM with messages.")
                reply = self.llm.invoke(messages)
                logger.debug(f"LLM response received: {reply}")

                parsed_reply = self.parse_llmresult(reply)
                logger.debug(f"Parsed LLM reply: {parsed_reply}")

                # Log the request and response
                model_name = self.llm.model.model_name if hasattr(self.llm.model, 'model_name') else "unknown_model"

                LLMLogger.log_request(prompts=messages, parsed_reply=parsed_reply, model_name=model_name)
                logger.debug("Request successfully logged.")

                # Ensure that reply is an instance of AIMessage
                if isinstance(reply, AIMessage):
                    return reply
                elif isinstance(reply, dict) and 'content' in reply:
                    return AIMessage(content=reply['content'])
                else:
                    logger.error(f"Unexpected reply format: {reply}")
                    raise ValueError("Unexpected reply format from LLM.")
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTPStatusError encountered: {e}")
                if e.response.status_code == 429:
                    retry_after = e.response.headers.get('retry-after')
                    retry_after_ms = e.response.headers.get('retry-after-ms')

                    if retry_after:
                        wait_time = int(retry_after)
                        logger.warning(
                            f"Rate limit exceeded. Waiting for {wait_time} seconds before retrying (from 'retry-after').")
                        time.sleep(wait_time)
                    elif retry_after_ms:
                        wait_time = int(retry_after_ms) / 1000.0
                        logger.warning(
                            f"Rate limit exceeded. Waiting for {wait_time} seconds before retrying (from 'retry-after-ms').")
                        time.sleep(wait_time)
                    else:
                        wait_time = 30
                        logger.warning(
                            f"'retry-after' header not found. Waiting for {wait_time} seconds before retrying (default).")
                        time.sleep(wait_time)
                else:
                    logger.error(f"HTTP error with status code: {e.response.status_code}. Waiting 30 seconds before retrying.")
                    time.sleep(30)

            except Exception as e:
                logger.error(f"Unexpected error occurred: {e}")
                logger.info("Waiting for 30 seconds before retrying due to an unexpected error.")
                time.sleep(30)

    def parse_llmresult(self, llmresult: AIMessage) -> Dict[str, Dict]:
        """
        Parse the result returned by the AI model into a structured dictionary.

        Args:
            llmresult (AIMessage): The raw response from the AI model.

        Returns:
            Dict[str, Dict]: The parsed response containing content, metadata, and token usage.

        Raises:
            KeyError: If expected keys are missing in the response.
            Exception: For any other errors during parsing.
        """
        logger.debug(f"Parsing LLM result: {llmresult}")

        try:
            if hasattr(llmresult, 'usage_metadata'):
                content = llmresult.content
                response_metadata = llmresult.response_metadata
                id_ = llmresult.id
                usage_metadata = llmresult.usage_metadata

                parsed_result = {
                    "content": content,
                    "response_metadata": {
                        "model_name": response_metadata.get("model_name", ""),
                        "system_fingerprint": response_metadata.get("system_fingerprint", ""),
                        "finish_reason": response_metadata.get("finish_reason", ""),
                        "logprobs": response_metadata.get("logprobs", None),
                    },
                    "id": id_,
                    "usage_metadata": {
                        "input_tokens": usage_metadata.get("input_tokens", 0),
                        "output_tokens": usage_metadata.get("output_tokens", 0),
                        "total_tokens": usage_metadata.get("total_tokens", 0),
                    },
                }
            else:
                content = llmresult.content
                response_metadata = llmresult.response_metadata
                id_ = llmresult.id
                token_usage = response_metadata.get('token_usage', {})

                parsed_result = {
                    "content": content,
                    "response_metadata": {
                        "model_name": response_metadata.get("model", ""),
                        "finish_reason": response_metadata.get("finish_reason", ""),
                    },
                    "id": id_,
                    "usage_metadata": {
                        "input_tokens": token_usage.get("prompt_tokens", 0),
                        "output_tokens": token_usage.get("completion_tokens", 0),
                        "total_tokens": token_usage.get("total_tokens", 0),
                    },
                }
            logger.debug(f"Parsed LLM result successfully: {parsed_result}")
            return parsed_result

        except KeyError as e:
            logger.error(f"KeyError while parsing LLM result: missing key {e}")
            raise

        except Exception as e:
            logger.error(f"Unexpected error while parsing LLM result: {e}")
            raise
