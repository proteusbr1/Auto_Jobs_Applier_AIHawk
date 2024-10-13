# llm_manager.py

import json
import os
import re
import textwrap
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Union, Optional

import httpx
from Levenshtein import distance
from dotenv import load_dotenv
from langchain_core.messages import BaseMessage
from langchain_core.messages.ai import AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompt_values import StringPromptValue, ChatPromptValue
from langchain_core.prompts import ChatPromptTemplate

import src.strings as strings
from src.job import Job
from loguru import logger
from app_config import USER_RESUME_SUMMARY

# Load environment variables from a .env file
load_dotenv()


class AIModel(ABC):
    """
    Abstract base class for AI models.
    Defines the interface that all AI models must implement.
    """

    @abstractmethod
    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke the AI model with the given prompt.

        Args:
            prompt (str): The input prompt for the AI model.

        Returns:
            BaseMessage: The response from the AI model.
        """
        pass


class OpenAIModel(AIModel):
    """
    Implementation of the AIModel interface for OpenAI models.
    """

    def __init__(self, api_key: str, llm_model: str):
        """
        Initialize the OpenAIModel with the specified API key and model name.

        Args:
            api_key (str): The API key for OpenAI.
            llm_model (str): The name of the OpenAI model to use.
        """
        from langchain_openai import ChatOpenAI
        self.model = ChatOpenAI(model_name=llm_model, openai_api_key=api_key, temperature=0.4)
        logger.debug(f"OpenAIModel initialized with model: {llm_model}")

    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke the OpenAI API with the given prompt.

        Args:
            prompt (str): The input prompt for the OpenAI model.

        Returns:
            BaseMessage: The response from the OpenAI API.

        Raises:
            Exception: If an error occurs while invoking the API.
        """
        logger.debug("Invoking OpenAI API.")
        try:
            response = self.model.invoke(prompt)
            logger.debug("OpenAI API invoked successfully.")
            return response
        except Exception as e:
            logger.error(f"Error invoking OpenAI API: {e}")
            raise


class ClaudeModel(AIModel):
    """
    Implementation of the AIModel interface for Claude models.
    """

    def __init__(self, api_key: str, llm_model: str):
        """
        Initialize the ClaudeModel with the specified API key and model name.

        Args:
            api_key (str): The API key for Claude.
            llm_model (str): The name of the Claude model to use.
        """
        from langchain_anthropic import ChatAnthropic
        self.model = ChatAnthropic(model=llm_model, api_key=api_key, temperature=0.4)
        logger.debug(f"ClaudeModel initialized with model: {llm_model}")

    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke the Claude API with the given prompt.

        Args:
            prompt (str): The input prompt for the Claude model.

        Returns:
            BaseMessage: The response from the Claude API.

        Raises:
            Exception: If an error occurs while invoking the API.
        """
        logger.debug("Invoking Claude API.")
        try:
            response = self.model.invoke(prompt)
            logger.debug("Claude API invoked successfully.")
            return response
        except Exception as e:
            logger.error(f"Error invoking Claude API: {e}")
            raise


class OllamaModel(AIModel):
    """
    Implementation of the AIModel interface for Ollama models.
    """

    def __init__(self, llm_model: str, llm_api_url: str):
        """
        Initialize the OllamaModel with the specified model name and API URL.

        Args:
            llm_model (str): The name of the Ollama model to use.
            llm_api_url (str): The API URL for Ollama.
        """
        from langchain_ollama import ChatOllama

        if llm_api_url:
            logger.debug(f"Using Ollama with API URL: {llm_api_url}")
            self.model = ChatOllama(model=llm_model, base_url=llm_api_url)
        else:
            self.model = ChatOllama(model=llm_model)
            logger.debug(f"Using Ollama with default API URL for model: {llm_model}")

    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke the Ollama API with the given prompt.

        Args:
            prompt (str): The input prompt for the Ollama model.

        Returns:
            BaseMessage: The response from the Ollama API.

        Raises:
            Exception: If an error occurs while invoking the API.
        """
        logger.debug("Invoking Ollama API.")
        try:
            response = self.model.invoke(prompt)
            logger.debug("Ollama API invoked successfully.")
            return response
        except Exception as e:
            logger.error(f"Error invoking Ollama API: {e}")
            raise


class GeminiModel(AIModel):
    """
    Implementation of the AIModel interface for Gemini models.
    """

    def __init__(self, api_key: str, llm_model: str):
        """
        Initialize the GeminiModel with the specified API key and model name.

        Args:
            api_key (str): The API key for Gemini.
            llm_model (str): The name of the Gemini model to use.
        """
        from langchain_google_genai import ChatGoogleGenerativeAI, HarmBlockThreshold, HarmCategory
        self.model = ChatGoogleGenerativeAI(
            model=llm_model,
            google_api_key=api_key,
            safety_settings={
                HarmCategory.HARM_CATEGORY_UNSPECIFIED: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DEROGATORY: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_TOXICITY: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_VIOLENCE: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUAL: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_MEDICAL: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE
            }
        )
        logger.debug(f"GeminiModel initialized with model: {llm_model}")

    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke the Gemini API with the given prompt.

        Args:
            prompt (str): The input prompt for the Gemini model.

        Returns:
            BaseMessage: The response from the Gemini API.

        Raises:
            Exception: If an error occurs while invoking the API.
        """
        logger.debug("Invoking Gemini API.")
        try:
            response = self.model.invoke(prompt)
            logger.debug("Gemini API invoked successfully.")
            return response
        except Exception as e:
            logger.error(f"Error invoking Gemini API: {e}")
            raise


class HuggingFaceModel(AIModel):
    """
    Implementation of the AIModel interface for Hugging Face models.
    """

    def __init__(self, api_key: str, llm_model: str):
        """
        Initialize the HuggingFaceModel with the specified API key and model name.

        Args:
            api_key (str): The API key for Hugging Face.
            llm_model (str): The name of the Hugging Face model to use.
        """
        from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
        self.model = HuggingFaceEndpoint(repo_id=llm_model, huggingfacehub_api_token=api_key, temperature=0.4)
        self.chatmodel = ChatHuggingFace(llm=self.model)
        logger.debug(f"HuggingFaceModel initialized with model: {llm_model}")

    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke the Hugging Face API with the given prompt.

        Args:
            prompt (str): The input prompt for the Hugging Face model.

        Returns:
            BaseMessage: The response from the Hugging Face API.

        Raises:
            Exception: If an error occurs while invoking the API.
        """
        logger.debug("Invoking Hugging Face API.")
        try:
            response = self.chatmodel.invoke(prompt)
            logger.debug("Hugging Face API invoked successfully.")
            return response
        except Exception as e:
            logger.error(f"Error invoking Hugging Face API: {e}")
            raise


class AIAdapter:
    """
    Adapter class to abstract the interaction with different AI models.
    """

    def __init__(self, config: dict, api_key: str):
        """
        Initialize the AIAdapter with the given configuration and API key.

        Args:
            config (dict): Configuration dictionary containing model details.
            api_key (str): The API key for the selected AI model.
        """
        self.model = self._create_model(config, api_key)
        logger.debug("AIAdapter initialized with model.")

    def _create_model(self, config: dict, api_key: str) -> AIModel:
        """
        Create an instance of the appropriate AIModel based on the configuration.

        Args:
            config (dict): Configuration dictionary containing model details.
            api_key (str): The API key for the selected AI model.

        Returns:
            AIModel: An instance of a subclass of AIModel.

        Raises:
            ValueError: If the model type specified in the configuration is unsupported.
        """
        llm_model_type = config.get('llm_model_type')
        llm_model = config.get('llm_model')
        llm_api_url = config.get('llm_api_url', "")

        logger.debug(f"Using model type: {llm_model_type} with model: {llm_model}")

        if llm_model_type == "openai":
            return OpenAIModel(api_key, llm_model)
        elif llm_model_type == "claude":
            return ClaudeModel(api_key, llm_model)
        elif llm_model_type == "ollama":
            return OllamaModel(llm_model, llm_api_url)
        elif llm_model_type == "gemini":
            return GeminiModel(api_key, llm_model)
        elif llm_model_type == "huggingface":
            return HuggingFaceModel(api_key, llm_model)
        else:
            logger.error(f"Unsupported model type: {llm_model_type}")
            raise ValueError(f"Unsupported model type: {llm_model_type}")

    def invoke(self, prompt: str) -> str:
        """
        Invoke the selected AI model with the given prompt.

        Args:
            prompt (str): The input prompt for the AI model.

        Returns:
            str: The response from the AI model.

        Raises:
            Exception: If an error occurs while invoking the model.
        """
        logger.debug("AIAdapter invoking model.")
        try:
            return self.model.invoke(prompt)
        except Exception as e:
            logger.error(f"Error invoking model through AIAdapter: {e}")
            raise


class LLMLogger:
    """
    Logger class for logging AI model interactions.
    """

    def __init__(self, llm: Union[OpenAIModel, OllamaModel, ClaudeModel, GeminiModel, HuggingFaceModel]):
        """
        Initialize the LLMLogger with the given AI model.

        Args:
            llm (Union[OpenAIModel, OllamaModel, ClaudeModel, GeminiModel, HuggingFaceModel]): The AI model instance.
        """
        self.llm = llm
        logger.debug(f"LLMLogger initialized with LLM: {self.llm}")

    @staticmethod
    def log_request(prompts: Union[List[BaseMessage], StringPromptValue, Dict], parsed_reply: Dict[str, Dict]):
        """
        Log the details of an AI model request and its response.

        Args:
            prompts (Union[List[BaseMessage], StringPromptValue, Dict]): The prompts sent to the AI model.
            parsed_reply (Dict[str, Dict]): The parsed response from the AI model.

        Raises:
            Exception: If an error occurs during logging.
        """
        logger.debug("Starting log_request method.")
        logger.debug(f"Prompts received: {prompts}")
        logger.debug(f"Parsed reply received: {parsed_reply}")

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
            logger.debug(f"Model name: {model_name}")
        except AttributeError as e:
            logger.error(f"AttributeError in response_metadata: {e}")
            raise

        try:
            prompt_price_per_token = 0.00000015
            completion_price_per_token = 0.0000006
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

    def __init__(self, llm: Union[OpenAIModel, OllamaModel, ClaudeModel, GeminiModel, HuggingFaceModel]):
        """
        Initialize the LoggerChatModel with the given AI model.

        Args:
            llm (Union[OpenAIModel, OllamaModel, ClaudeModel, GeminiModel, HuggingFaceModel]): The AI model instance.
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

                LLMLogger.log_request(prompts=messages, parsed_reply=parsed_reply)
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


class GPTAnswerer:
    """
    Class responsible for handling interactions with the AI model to answer questions,
    evaluate jobs, and manage resumes.
    """

    def __init__(self, config: dict, llm_api_key: str):
        """
        Initialize the GPTAnswerer with the given configuration and API key.

        Args:
            config (dict): Configuration dictionary containing model details.
            llm_api_key (str): The API key for the AI model.
        """
        self.ai_adapter = AIAdapter(config, llm_api_key)
        self.llm_cheap = LoggerChatModel(self.ai_adapter)
        self.job = None
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

    def set_job(self, title: str, company: str, location: str, link: str, apply_method: str,
                description: Optional[str] = "", recruiter_link: Optional[str] = ""):
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
            description=description,
            recruiter_link=recruiter_link
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

    def answer_question_textual_wide_range(self, question: str, job: Job = None) -> str:
        """
        Answer a wide-range textual question based on the job and resume.

        Args:
            question (str): The question to answer.
            job (Job, optional): The job object. If provided, it will set the current job.

        Returns:
            str: The answer to the question.

        Raises:
            ValueError: If the job parameter is None or required attributes are missing.
            Exception: If an error occurs during the process.
        """
        logger.debug(f"Answering textual question: {question}")

        if job:
            logger.debug(f"Setting job information: {job.title} at {job.company}")
            self.set_job(
                title=job.title,
                company=job.company,
                location=job.location,
                link=job.link,
                apply_method=job.apply_method,
                description=job.description,
                recruiter_link=job.recruiter_link,
            )
        else:
            logger.error("Job parameter is None.")
            raise ValueError("Job parameter cannot be None.")

        try:
            if self.job is None:
                logger.error("Job object is None. Cannot proceed with answering the question.")
                raise ValueError("Job object is None. Please set the job first using set_job().")

            if not hasattr(self.job, 'description'):
                logger.error("Job object does not have a 'description' attribute.")
                raise AttributeError("Job object does not have a 'description' attribute.")

            # Define chains for different sections
            chains = {
                "personal_information": self._create_chain(strings.personal_information_template),
                "self_identification": self._create_chain(strings.self_identification_template),
                "legal_authorization": self._create_chain(strings.legal_authorization_template),
                "work_preferences": self._create_chain(strings.work_preferences_template),
                "education_details": self._create_chain(strings.education_details_template),
                "experience_details": self._create_chain(strings.experience_details_template),
                "projects": self._create_chain(strings.projects_template),
                "availability": self._create_chain(strings.availability_template),
                "salary_expectations": self._create_chain(strings.salary_expectations_template),
                "certifications": self._create_chain(strings.certifications_template),
                "languages": self._create_chain(strings.languages_template),
                "interests": self._create_chain(strings.interests_template),
                "cover_letter": self._create_chain(strings.coverletter_template),
            }

            section_prompt = """
You are assisting a bot designed to automatically apply for jobs on AIHawk. The bot receives various questions about job applications and needs to determine the most relevant section of the resume to provide an accurate response.

For the following question: '{question}', determine which section of the resume is most relevant. 
Respond with exactly one of the following options:
- Personal information
- Self Identification
- Legal Authorization
- Work Preferences
- Education Details
- Experience Details
- Projects
- Availability
- Salary Expectations
- Certifications
- Languages
- Interests
- Cover letter

Here are detailed guidelines to help you choose the correct section:

1. **Personal Information**:
- **Purpose**: Contains your basic contact details and online profiles.
- **Use When**: The question is about how to contact you or requests links to your professional online presence.
- **Examples**: Email address, phone number, AIHawk profile, GitHub repository, personal website.

2. **Self Identification**:
- **Purpose**: Covers personal identifiers and demographic information.
- **Use When**: The question pertains to your gender, pronouns, veteran status, disability status, or ethnicity.
- **Examples**: Gender, pronouns, veteran status, disability status, ethnicity.

3. **Legal Authorization**:
- **Purpose**: Details your work authorization status and visa requirements.
- **Use When**: The question asks about your ability to work in specific countries or if you need sponsorship or visas.
- **Examples**: Work authorization in EU and US, visa requirements, legally allowed to work.

4. **Work Preferences**:
- **Purpose**: Specifies your preferences regarding work conditions and job roles.
- **Use When**: The question is about your preferences for remote work, in-person work, relocation, and willingness to undergo assessments or background checks.
- **Examples**: Remote work, in-person work, open to relocation, willingness to complete assessments.

5. **Education Details**:
- **Purpose**: Contains information about your academic qualifications.
- **Use When**: The question concerns your degrees, universities attended, GPA, and relevant coursework.
- **Examples**: Degree, university, GPA, field of study, exams.

6. **Experience Details**:
- **Purpose**: Details your professional work history and key responsibilities.
- **Use When**: The question pertains to your job roles, responsibilities, and achievements in previous positions.
- **Examples**: Job positions, company names, key responsibilities, skills acquired.

7. **Projects**:
- **Purpose**: Highlights specific projects you have worked on.
- **Use When**: The question asks about particular projects, their descriptions, or links to project repositories.
- **Examples**: Project names, descriptions, links to project repositories.

8. **Availability**:
- **Purpose**: Provides information on your availability for new roles.
- **Use When**: The question is about how soon you can start a new job or your notice period.
- **Examples**: Notice period, availability to start.

9. **Salary Expectations**:
- **Purpose**: Covers your expected salary range.
- **Use When**: The question pertains to your salary expectations or compensation requirements.
- **Examples**: Desired salary range.

10. **Certifications**:
    - **Purpose**: Lists your professional certifications or licenses.
    - **Use When**: The question involves your certifications or qualifications from recognized organizations.
    - **Examples**: Certification names, issuing bodies, dates of validity.

11. **Languages**:
    - **Purpose**: Describes the languages you can speak and your proficiency levels.
    - **Use When**: The question asks about your language skills or proficiency in specific languages.
    - **Examples**: Languages spoken, proficiency levels.

12. **Interests**:
    - **Purpose**: Details your personal or professional interests.
    - **Use When**: The question is about your hobbies, interests, or activities outside of work.
    - **Examples**: Personal hobbies, professional interests.

13. **Cover Letter**:
    - **Purpose**: Contains your personalized cover letter or statement.
    - **Use When**: The question involves your cover letter or specific written content intended for the job application.
    - **Examples**: Cover letter content, personalized statements.

Provide only the exact name of the section from the list above with no additional text.
"""

            # Create and invoke the chain to determine the relevant section
            prompt = ChatPromptTemplate.from_template(section_prompt)
            chain = prompt | self.llm_cheap | StrOutputParser()
            output = chain.invoke({"question": question})
            logger.debug(f"Section determination response: {output}")

            # Extract the section name from the response using regex
            match = re.search(
                r"(Personal information|Self Identification|Legal Authorization|Work Preferences|Education "
                r"Details|Experience Details|Projects|Availability|Salary "
                r"Expectations|Certifications|Languages|Interests|Cover letter)",
                output, re.IGNORECASE)
            if not match:
                logger.error("Could not extract section name from the response.")
                raise ValueError("Could not extract section name from the response.")

            section_name = match.group(1).lower().replace(" ", "_")
            logger.debug(f"Determined section name: {section_name}")

            if section_name == "cover_letter":
                chain = chains.get(section_name)
                if not chain:
                    logger.error(f"Chain not defined for section '{section_name}'")
                    raise ValueError(f"Chain not defined for section '{section_name}'")
                output = chain.invoke({"resume": self.resume, "job_description": self.job_description})
                logger.debug(f"Cover letter generated: {output}")
                return output

            # Retrieve the relevant section from the resume or job application profile
            resume_section = getattr(self.resume, section_name, None) or getattr(self.job_application_profile, section_name, None)
            if resume_section is None:
                logger.error(f"Section '{section_name}' not found in either resume or job_application_profile.")
                raise ValueError(f"Section '{section_name}' not found in either resume or job_application_profile.")

            # Invoke the appropriate chain for the determined section
            chain = chains.get(section_name)
            if not chain:
                logger.error(f"Chain not defined for section '{section_name}'")
                raise ValueError(f"Chain not defined for section '{section_name}'")
            output = chain.invoke({"resume_section": resume_section, "question": question})
            logger.debug(f"Question answered: {output}")
            return output

        except Exception as e:
            logger.error(f"Error answering textual wide range question: {e}")
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

    def evaluate_job(self, job: Job, resume_prompt: str) -> float:
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

        # Create the prompt for evaluating the job and resume
        prompt = f"""
You are a Human Resources expert specializing in evaluating job applications for the American job market. Your task is to assess the compatibility between the following job description and a provided resume. 
Return only a score from 0 to 10 representing the candidate's likelihood of securing the position, with 0 being the lowest probability and 10 being the highest. 
The assessment should consider HR-specific criteria for the American job market, including skills, experience, education, and any other relevant criteria mentioned in the job description.

Job Title: 
{job_title}

Job Description:
{job_description}

Resume:
{resume_prompt}

Score (0 to 10):
"""

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
                    return 0.0  # Returns 0.0 if the score is out of the expected range
            else:
                logger.error(f"Could not find a valid score in response: {response}")
                return 0.1  # Returns 0.1 if no valid score is found

        except Exception as e:
            logger.error(f"Error processing the score from response: {e}", exc_info=True)
            return 0.1  # Returns 0.1 in case of an error

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
        
        Returns:
            str: The answer generated by the model.
        
        Raises:
            Exception: If an error occurs during the invocation of the model.
        """
        logger.debug(f"Answering simple question: {question}")
        
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
                    description=job.description,
                    recruiter_link=job.recruiter_link,
                )
            else:
                logger.error("The 'job' parameter is None.")
                raise ValueError("The 'job' parameter cannot be None.")
            
            if self.job is None:
                logger.error("Job object is None. Configure the job first using set_job().")
                raise ValueError("Job object is None. Configure the job first using set_job().")
            
            # Create the prompt following the specified rules
            prompt_template = """
            You are an AI assistant specializing in human resources and knowledgeable about the American job market. Your role is to help me secure a job by answering questions related to my resume and a job description. Follow these rules:
            - Answer questions directly.
            - Keep the answer under {limit_caractere} characters.
            - If not sure, provide an approximate answer.

            Job Title:
            ({job_title})

            Job Description:
            ({job_description})

            Resume:
            ({resume})

            Question:
            ({question})

            Answer:
            """
            
            # Prepare the prompt USER_RESUME_SUMMARY
            today_date = datetime.now().strftime("%Y-%m-%d")  # Formato YYYY-MM-DD
            formatted_resume = USER_RESUME_SUMMARY.replace("{today_date}", today_date)

            # Prepare the prompt with the necessary information
            prompt = ChatPromptTemplate.from_template(prompt_template)
            formatted_prompt = prompt.format(
                limit_caractere=limit_caractere,
                job_title=self.job.title,
                job_description=self.job.description,
                resume=formatted_resume,
                question=question
            )
            
            # Invoke the model
            response = self.ai_adapter.invoke(formatted_prompt)
            logger.debug(f"Response received from the model: {response.content}")
            
            # Extract the content from the response
            if isinstance(response, AIMessage):
                answer = response.content.strip()
            elif isinstance(response, dict) and 'content' in response:
                answer = response['content'].strip()
            else:
                logger.error(f"Unexpected response format: {response}")
                raise ValueError("Unexpected response format from the model.")
            
            # Ensure the answer is within 140 characters
            if len(answer) > 140:
                answer = answer[:137] + "..."
                logger.debug(f"Answer truncated to 140 characters: {answer}")
            
            return answer
        
        except Exception as e:
            logger.error(f"Error answering the simple question: {e}", exc_info=True)
            raise
