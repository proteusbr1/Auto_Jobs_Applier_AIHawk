# src/llm/interaction_logger.py
"""
Handles logging of LLM interactions, including prompts, responses, token usage, and cost.

Provides a wrapper class (`LoggingModelWrapper`) to automatically log interactions
when an AI model is invoked, and helper functions for parsing and formatting log data.
"""

import json
import time
import traceback
from datetime import datetime
from typing import Dict, List, Union, Optional, Any, Final

import httpx # For specific error handling
from loguru import logger
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.prompt_values import StringPromptValue, ChatPromptValue

from .models import AIModel
from .utils.pricing import get_model_pricing
from .utils.helpers import parse_prompts_for_logging, format_datetime
from .config import LLM_LOG_FILE_PATH # Use configured path
from .exceptions import LoggingError, LLMParsingError, LLMInvocationError


# --- Logging Function ---

def log_interaction(
    *, # Enforce keyword arguments for clarity
    model_name: str,
    start_time: datetime,
    end_time: datetime,
    prompts: Union[List[BaseMessage], StringPromptValue, ChatPromptValue, Dict, str],
    parsed_response: Dict[str, Any],
    log_file_path: str = LLM_LOG_FILE_PATH
) -> None:
    """
    Logs the details of a single LLM interaction to a JSON file.

    Args:
        model_name (str): The name of the AI model used.
        start_time (datetime): Timestamp when the request started.
        end_time (datetime): Timestamp when the response was received.
        prompts: The original prompts sent to the model.
        parsed_response (Dict[str, Any]): The parsed response from the AI model,
                                           expected to contain 'content', 'response_metadata',
                                           and 'usage_metadata'.
        log_file_path (str): The path to the JSON log file.
    """
    logger.debug(f"Attempting to log interaction for model: {model_name}")

    try:
        # 1. Parse Prompts
        parsed_prompts = parse_prompts_for_logging(prompts)

        # 2. Extract Response Details
        response_content = parsed_response.get("content", "N/A")
        response_metadata = parsed_response.get("response_metadata", {})
        usage_metadata = parsed_response.get("usage_metadata", {})
        response_id = parsed_response.get("id", "N/A") # Get response ID if available

        # Ensure model name from response metadata is used if available, otherwise use the passed one
        logged_model_name = response_metadata.get("model_name") or model_name
        if not logged_model_name or logged_model_name == "unknown_model":
             logger.warning(f"Model name for logging is missing or unknown. Using passed name: {model_name}")
             logged_model_name = model_name


        # 3. Extract Token Usage
        input_tokens = usage_metadata.get("input_tokens", 0)
        output_tokens = usage_metadata.get("output_tokens", 0)
        total_tokens = usage_metadata.get("total_tokens", input_tokens + output_tokens) # Calculate if not present

        # Log a warning if token data seems incomplete or estimated
        if not usage_metadata or not all(k in usage_metadata for k in ["input_tokens", "output_tokens", "total_tokens"]):
             logger.warning(f"Incomplete or estimated token usage for model {logged_model_name}. Logged values: In={input_tokens}, Out={output_tokens}, Total={total_tokens}")


        # 4. Calculate Cost
        pricing = get_model_pricing(logged_model_name)
        input_cost = input_tokens * pricing.get("input_token_price", 0.0)
        output_cost = output_tokens * pricing.get("output_token_price", 0.0)
        total_cost = input_cost + output_cost

        # 5. Calculate Duration
        duration = (end_time - start_time).total_seconds()

        # 6. Format Log Entry
        log_entry = {
            "model_used": logged_model_name,
            "request_id": response_id, # Include if available
            "timestamp_utc": format_datetime(datetime.utcnow()), # Log UTC time
            "start_time_local": format_datetime(start_time),
            "end_time_local": format_datetime(end_time),
            "duration_seconds": round(duration, 3),
            "prompts": parsed_prompts,
            "response": response_content,
            "token_usage": {
                "input": input_tokens,
                "output": output_tokens,
                "total": total_tokens,
            },
            "cost_usd": {
                "input": round(input_cost, 8),
                "output": round(output_cost, 8),
                "total": round(total_cost, 8),
                "pricing_used": pricing # Log the pricing rates applied
            },
            "response_metadata": response_metadata, # Include full metadata for debugging
        }

        # 7. Write to Log File
        log_entry_json = json.dumps(log_entry, ensure_ascii=False, indent=4)
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write(log_entry_json + ",\n") # Append comma for valid JSON array (manually close array bracket externally if needed)

        logger.debug(f"Successfully logged interaction to {log_file_path}")

    except Exception as e:
        logger.error(f"Failed to log LLM interaction: {e}", exc_info=True)
        # Do not raise LoggingError by default, as logging failure shouldn't stop the main flow
        # However, specific handling might be needed depending on requirements.


# --- Parsing Helper ---

def _parse_llm_result(llm_result: Any, model_instance: AIModel) -> Dict[str, Any]:
    """
    Parses the raw result from an AIModel's invoke method into a standardized dictionary.

    Handles common result types like AIMessage, strings, or dicts. Attempts to extract
    content, metadata, and usage information. Includes basic token estimation as a fallback
    if usage metadata is missing.

    Args:
        llm_result (Any): The raw response from the AI model's invoke method.
        model_instance (AIModel): The AIModel instance that produced the result (used for model name fallback).

    Returns:
        Dict[str, Any]: A dictionary with keys 'content', 'response_metadata', 'usage_metadata', 'id'.

    Raises:
        LLMParsingError: If the result format is unknown or essential data cannot be extracted.
    """
    logger.debug(f"Parsing LLM result of type: {type(llm_result)}")
    parsed_data = {
        "content": None,
        "response_metadata": {},
        "usage_metadata": {},
        "id": None,
    }
    model_name_fallback = model_instance.get_pricing_model_name() # Use pricing name for consistency

    try:
        if isinstance(llm_result, AIMessage):
            logger.debug("Parsing AIMessage result.")
            parsed_data["content"] = llm_result.content
            parsed_data["id"] = llm_result.id
            # AIMessage structure can vary slightly based on provider/Langchain version
            parsed_data["response_metadata"] = getattr(llm_result, 'response_metadata', {}) or {}
            parsed_data["usage_metadata"] = getattr(llm_result, 'usage_metadata', {}) or {}

            # Ensure model_name is present in response_metadata
            if "model_name" not in parsed_data["response_metadata"]:
                 parsed_data["response_metadata"]["model_name"] = model_name_fallback

            # Handle cases where token usage might be nested differently (e.g., older OpenAI)
            if not parsed_data["usage_metadata"] and "token_usage" in parsed_data["response_metadata"]:
                 token_usage = parsed_data["response_metadata"].get("token_usage", {})
                 parsed_data["usage_metadata"] = {
                     "input_tokens": token_usage.get("prompt_tokens", 0),
                     "output_tokens": token_usage.get("completion_tokens", 0),
                     "total_tokens": token_usage.get("total_tokens", 0),
                 }
                 # Calculate total if missing
                 if parsed_data["usage_metadata"]["total_tokens"] == 0:
                      parsed_data["usage_metadata"]["total_tokens"] = parsed_data["usage_metadata"]["input_tokens"] + parsed_data["usage_metadata"]["output_tokens"]


        elif isinstance(llm_result, str):
            logger.debug("Parsing raw string result. Estimating token usage.")
            parsed_data["content"] = llm_result
            parsed_data["id"] = "string_response_" + str(time.time()) # Generate simple ID

            # Basic estimation (highly inaccurate, use only as last resort)
            output_tokens_est = max(1, len(llm_result) // 4) # At least 1 token
            # Cannot know input tokens from string output alone, make a wild guess
            input_tokens_est = output_tokens_est * 2 # Guess input was twice the output
            total_tokens_est = input_tokens_est + output_tokens_est

            parsed_data["response_metadata"] = {
                 "model_name": model_name_fallback,
                 "finish_reason": "unknown_from_string",
                 "estimated_usage": True # Flag that usage is estimated
            }
            parsed_data["usage_metadata"] = {
                 "input_tokens": input_tokens_est,
                 "output_tokens": output_tokens_est,
                 "total_tokens": total_tokens_est,
            }

        elif isinstance(llm_result, dict):
            # Handle potential dictionary structures (less common with LangChain now)
            logger.debug("Parsing dictionary result.")
            parsed_data["content"] = llm_result.get("content", str(llm_result)) # Fallback to string
            parsed_data["id"] = llm_result.get("id", "dict_response_" + str(time.time()))
            # Try to find metadata, might need provider-specific logic
            parsed_data["response_metadata"] = llm_result.get("response_metadata", {"model_name": model_name_fallback})
            parsed_data["usage_metadata"] = llm_result.get("usage_metadata", {})
            if not parsed_data["usage_metadata"]:
                # Add estimation logic like for strings if necessary
                 logger.warning("Dictionary result lacks usage_metadata. Token usage will be missing/estimated.")


        else:
            # Unknown format
            logger.error(f"Unexpected LLM result format encountered: {type(llm_result)}")
            raise LLMParsingError(f"Cannot parse unexpected LLM result format: {type(llm_result)}")

        # Final checks and cleanup
        if parsed_data["content"] is None:
            logger.warning("Parsed LLM content is None.")
            parsed_data["content"] = "" # Ensure content is always a string

        if not parsed_data["usage_metadata"].get("total_tokens", 0) > 0:
             # If tokens are still zero after parsing/estimation, log warning
              logger.warning(f"Parsed token usage seems zero for model {model_name_fallback}. Check LLM response structure or estimation logic.")


        logger.debug(f"Successfully parsed LLM result. Content length: {len(str(parsed_data['content']))}, Tokens: {parsed_data['usage_metadata']}")
        return parsed_data

    except Exception as e:
        logger.error(f"Error during LLM result parsing: {e}\nRaw Result: {str(llm_result)[:500]}...", exc_info=True)
        # Wrap the original exception
        raise LLMParsingError(f"Failed to parse LLM result: {e}") from e


# --- Logging Wrapper Class ---

class LoggingModelWrapper:
    """
    A wrapper around an AIModel instance that automatically logs interactions.

    Handles invocation, response parsing, error handling (including retries for
    rate limits), and triggers the logging function.
    """
    DEFAULT_RETRY_WAIT_SECONDS: Final[int] = 30
    MAX_RETRIES: Final[int] = 3 # Max retries for rate limit errors

    def __init__(self, model_instance: AIModel, log_file_path: str = LLM_LOG_FILE_PATH):
        """
        Initializes the wrapper.

        Args:
            model_instance (AIModel): The concrete AIModel instance to wrap.
            log_file_path (str): Path to the JSON file for logging interactions.
        """
        if not isinstance(model_instance, AIModel):
            raise TypeError(f"model_instance must be an instance of AIModel, not {type(model_instance)}")
        self.model = model_instance
        self.log_file_path = log_file_path
        logger.info(f"LoggingModelWrapper initialized for model: {self.model.get_model_name()}")
        logger.info(f"LLM interactions will be logged to: {self.log_file_path}")


    def invoke(self, prompts: Union[str, List[Dict[str, str]], List[BaseMessage], ChatPromptValue]) -> Any:
        """
        Invokes the wrapped AI model, handles retries, parses the response, logs the interaction,
        and returns the parsed content or a suitable response object.

        Args:
            prompts: The prompts to send to the model (various formats accepted).

        Returns:
            AIMessage or str: Typically returns an AIMessage containing the content and metadata,
                              or just the string content depending on the underlying model and parsing.

        Raises:
            LLMInvocationError: If the model invocation fails after retries.
            LLMParsingError: If the response cannot be parsed.
            Exception: For other unexpected errors.
        """
        retries = 0
        last_exception = None

        while retries <= self.MAX_RETRIES:
            start_time = datetime.now()
            try:
                logger.debug(f"Wrapper invoking model (Attempt {retries + 1}/{self.MAX_RETRIES + 1})")
                raw_response = self.model.invoke(prompts)
                end_time = datetime.now()
                logger.debug("Model invocation successful.")

                # Parse the raw response
                try:
                    parsed_response = _parse_llm_result(raw_response, self.model)
                except LLMParsingError as parse_error:
                    logger.error(f"Failed to parse LLM response: {parse_error}", exc_info=True)
                    # Log the attempt with parsing failure
                    log_interaction(
                        model_name=self.model.get_pricing_model_name(),
                        start_time=start_time,
                        end_time=end_time,
                        prompts=prompts,
                        parsed_response={"content": f"PARSING_ERROR: {parse_error}", "usage_metadata": {}, "response_metadata": {"error": str(parse_error)}},
                        log_file_path=self.log_file_path
                    )
                    raise # Re-raise the parsing error to the caller

                # Log the successful interaction
                log_interaction(
                    model_name=self.model.get_pricing_model_name(), # Use pricing name for logging cost
                    start_time=start_time,
                    end_time=end_time,
                    prompts=prompts,
                    parsed_response=parsed_response,
                    log_file_path=self.log_file_path
                )

                # Return a useful representation - AIMessage if possible, else content string
                # Check if original response was AIMessage to preserve type if needed downstream
                if isinstance(raw_response, AIMessage):
                    # Update content if parsing modified it (e.g., fallback)
                    # Be careful here, modifying the original AIMessage might have side effects
                    # Consider returning the parsed dict or a new AIMessage
                     # Return original AIMessage, assuming parsing mainly extracts data for logging
                    return raw_response
                    # Or return a new one based on parsed data:
                    # return AIMessage(content=parsed_response["content"], id=parsed_response["id"], response_metadata=parsed_response["response_metadata"], usage_metadata=parsed_response["usage_metadata"])

                elif isinstance(parsed_response.get("content"), str):
                    return parsed_response["content"] # Return string content if that's all we have
                else:
                     # Should not happen if parsing works correctly
                     logger.error("Parsed content is not string, returning raw response.")
                     return raw_response # Fallback


            except httpx.HTTPStatusError as e:
                last_exception = e
                if e.response.status_code == 429: # Rate limit error
                    retries += 1
                    if retries > self.MAX_RETRIES:
                         logger.error(f"Rate limit exceeded after {self.MAX_RETRIES} retries. Giving up.")
                         raise LLMInvocationError(f"Rate limit hit and max retries exceeded for {self.model.get_model_name()}") from e

                    # Determine wait time from headers
                    retry_after_sec = e.response.headers.get('retry-after')
                    retry_after_ms = e.response.headers.get('retry-after-ms')
                    wait_time = self.DEFAULT_RETRY_WAIT_SECONDS # Default wait

                    if retry_after_sec and retry_after_sec.isdigit():
                        wait_time = int(retry_after_sec)
                        logger.warning(f"Rate limit hit (429). Retrying after {wait_time} seconds (from 'retry-after' header). Attempt {retries}/{self.MAX_RETRIES}.")
                    elif retry_after_ms and retry_after_ms.isdigit():
                        wait_time = max(1, int(retry_after_ms) // 1000) # Convert ms to sec, ensure at least 1s
                        logger.warning(f"Rate limit hit (429). Retrying after {wait_time} seconds (from 'retry-after-ms' header). Attempt {retries}/{self.MAX_RETRIES}.")
                    else:
                        # Apply exponential backoff for default wait? e.g., wait_time = DEFAULT_RETRY_WAIT_SECONDS * (2 ** (retries - 1))
                        wait_time = self.DEFAULT_RETRY_WAIT_SECONDS
                        logger.warning(f"Rate limit hit (429). 'retry-after' headers not found/invalid. Retrying after default {wait_time} seconds. Attempt {retries}/{self.MAX_RETRIES}.")

                    time.sleep(wait_time)
                    continue # Go to next iteration of the while loop

                else:
                    # Other HTTP errors are likely not recoverable by retry
                    logger.error(f"HTTP error encountered: {e.response.status_code} - {e.response.text[:200]}...")
                    raise LLMInvocationError(f"HTTP error {e.response.status_code} invoking {self.model.get_model_name()}") from e

            except LLMInvocationError as e: # Catch errors raised by model.invoke()
                last_exception = e
                logger.error(f"LLM invocation failed: {e}", exc_info=True)
                # Potentially add retries for transient network errors? For now, fail fast.
                # Log the failed attempt before raising
                log_interaction(
                    model_name=self.model.get_pricing_model_name(),
                    start_time=start_time,
                    end_time=datetime.now(),
                    prompts=prompts,
                    parsed_response={"content": f"INVOCATION_ERROR: {e}", "usage_metadata": {}, "response_metadata": {"error": str(e)}},
                    log_file_path=self.log_file_path
                )
                raise # Re-raise the original invocation error

            except Exception as e: # Catch any other unexpected errors
                last_exception = e
                logger.critical(f"Unexpected error during model invocation or logging: {e}", exc_info=True)
                # Log the failed attempt if possible
                try:
                    log_interaction(
                        model_name=self.model.get_pricing_model_name(),
                        start_time=start_time,
                        end_time=datetime.now(),
                        prompts=prompts,
                        parsed_response={"content": f"UNEXPECTED_ERROR: {e}", "usage_metadata": {}, "response_metadata": {"error": str(e), "traceback": traceback.format_exc()}},
                        log_file_path=self.log_file_path
                    )
                except Exception as log_err:
                     logger.error(f"Additionally failed to log the unexpected error: {log_err}")

                raise LLMInvocationError(f"Unexpected error invoking model: {e}") from e # Wrap in standard error type

        # This point should only be reached if MAX_RETRIES is exceeded for a retriable error
        logger.error(f"Model invocation failed after {self.MAX_RETRIES + 1} attempts. Last error: {last_exception}")
        raise LLMInvocationError(f"Model invocation failed after maximum retries. Last error: {last_exception}") from last_exception

    def __call__(self, prompts: Union[List[Dict[str, str]], List[BaseMessage]]) -> AIMessage:
        """
        Makes the wrapper callable, primarily for compatibility with chains expecting
        a callable object that takes message lists and returns an AIMessage.

        Args:
            prompts: A list of message dictionaries or BaseMessage objects.

        Returns:
            AIMessage: The response from the AI model, wrapped in an AIMessage.

        Raises:
            ValueError: If the response format cannot be converted to AIMessage.
            LLMInvocationError: If the model invocation fails.
            LLMParsingError: If the response cannot be parsed.
        """
        logger.debug("LoggingModelWrapper invoked via __call__")
        # Use the main invoke method
        response = self.invoke(prompts)

        # Ensure the output is an AIMessage for compatibility
        if isinstance(response, AIMessage):
            return response
        elif isinstance(response, str):
             logger.warning("__call__ received string response, converting to AIMessage.")
             # Attempt to find relevant metadata from the log entry if needed, but likely lost here.
             # Create a minimal AIMessage.
             return AIMessage(content=response)
        else:
             logger.error(f"__call__ received unexpected response type: {type(response)}. Cannot convert to AIMessage.")
             raise ValueError(f"Unexpected response type from invoke: {type(response)}")