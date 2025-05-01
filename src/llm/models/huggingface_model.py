# src/llm/models/huggingface_model.py
"""
Concrete implementation of the AIModel interface for models hosted on Hugging Face Inference Endpoints or Hub.
Uses the `langchain-huggingface` package.
"""

from typing import Any, Union, List, Dict, Optional # Ensure Any is imported

from loguru import logger
# Ensure necessary LangChain components are imported
try:
    # Preferred import for dedicated HuggingFace integration
    from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
except ImportError:
     # Fallback for older community versions
     logger.warning("langchain_huggingface not found, falling back to langchain_community.")
     try:
         from langchain_community.llms import HuggingFaceEndpoint # LLM Interface
         # Chat wrapper might be different or need separate import
         # This part needs verification based on older community structure if used
         # For simplicity, assuming HuggingFaceEndpoint LLM interface is the target here
         # If Chat interface needed, adjust imports and usage
         ChatHuggingFace = None # Indicate Chat wrapper might not be available directly
     except ImportError:
          raise ImportError("Could not import HuggingFaceEndpoint from langchain_community or langchain_huggingface.")


from langchain_core.messages import BaseMessage, HumanMessage # For type hint and potential conversion
from langchain_core.prompt_values import ChatPromptValue # For type hint
# Import custom exceptions and base class
from .base_model import AIModel, LLMInvocationError, ConfigurationError


class HuggingFaceModel(AIModel):
    """
    AIModel implementation for interacting with models via Hugging Face Inference API
    (using `HuggingFaceEndpoint`). Assumes text-generation models.
    """

    def __init__(
        self,
        model_name: str, # This is the repo_id on Hugging Face Hub
        api_key: Optional[str] = None,
        temperature: Optional[float] = None,
        **kwargs: Any # Arguments for HuggingFaceEndpoint (e.g., task, endpoint_url)
    ):
        """
        Initializes the HuggingFaceModel.

        Args:
            model_name (str): The Hugging Face Hub repository ID of the model
                              (e.g., "mistralai/Mistral-7B-v0.1").
            api_key (Optional[str]): The Hugging Face API token (read token usually sufficient).
                                     If None, attempts to use `HUGGINGFACEHUB_API_TOKEN` environment variable.
            temperature (Optional[float]): The sampling temperature. Defaults to `AIModel.DEFAULT_TEMPERATURE`.
            **kwargs: Additional keyword arguments passed directly to `HuggingFaceEndpoint`.
                      Can include `endpoint_url` for dedicated inference endpoints, `task`, etc.
        """
        resolved_api_key = api_key
        # Set pricing name for clarity, though pricing varies wildly on HF
        self.pricing_model_name = f"huggingface/{model_name}"
        super().__init__(model_name=model_name, api_key=resolved_api_key, temperature=temperature, **kwargs)


    def _initialize_model(self) -> Any:
        """
        Initializes the LangChain `HuggingFaceEndpoint` instance (and optionally `ChatHuggingFace`).

        Returns:
            Any: The initialized LangChain client instance (either HuggingFaceEndpoint or ChatHuggingFace).

        Raises:
            ConfigurationError: If the API key is missing (and not in the environment).
            LLMInvocationError: If the client initialization fails.
            ImportError: If necessary HuggingFace libraries are missing.
        """
        logger.debug(f"Initializing HuggingFaceEndpoint for repo_id: {self.model_name}")

        if not self.api_key:
            import os
            if not os.getenv("HUGGINGFACEHUB_API_TOKEN"):
                raise ConfigurationError("HuggingFace API token not provided and HUGGINGFACEHUB_API_TOKEN environment variable is not set.")
            logger.warning("HuggingFace API token not directly provided, relying on environment variable.")

        try:
            # Primary client is the Endpoint interface
            endpoint_llm = HuggingFaceEndpoint(
                repo_id=self.model_name, # model_name is the repo_id here
                huggingfacehub_api_token=self.api_key, # Pass None if relying on env var
                temperature=self.temperature,
                # Pass other relevant kwargs, ensure 'task' is appropriate if needed
                **self.additional_kwargs
            )
            logger.debug("HuggingFaceEndpoint instance created successfully.")

            # If the ChatHuggingFace wrapper is available and desired, wrap the endpoint
            if ChatHuggingFace:
                 try:
                     chat_model = ChatHuggingFace(llm=endpoint_llm)
                     logger.debug("ChatHuggingFace wrapper created successfully.")
                     return chat_model # Return the chat interface if available
                 except Exception as chat_e:
                      logger.warning(f"Could not initialize ChatHuggingFace wrapper: {chat_e}. Falling back to HuggingFaceEndpoint LLM.")
                      return endpoint_llm # Fallback to the LLM interface
            else:
                 logger.warning("ChatHuggingFace wrapper not available/imported. Using HuggingFaceEndpoint LLM directly.")
                 return endpoint_llm # Return the LLM interface if chat wrapper not used

        except ImportError as e:
            logger.error(f"Missing HuggingFace library dependencies: {e}", exc_info=True)
            raise e # Re-raise import error
        except Exception as e:
            logger.error(f"Failed to initialize HuggingFaceEndpoint for repo '{self.model_name}': {e}", exc_info=True)
            raise LLMInvocationError(f"Failed to initialize HuggingFace client: {e}") from e


    def invoke(
        self,
        prompt: Union[str, List[Dict[str, str]], List[BaseMessage], ChatPromptValue]
    ) -> Any:
        """
        Invokes the initialized Hugging Face model with the provided prompt.

        Handles potential differences between invoking a Chat model vs. a base LLM.

        Args:
            prompt: The input prompt (string, message dict list, BaseMessage list, or ChatPromptValue).

        Returns:
            Any: The raw response from the LangChain model invoke call. This could be
                 an `AIMessage` (if using ChatHuggingFace) or a raw string response
                 (if using HuggingFaceEndpoint directly).

        Raises:
            LLMInvocationError: If the API call fails.
        """
        if self._model_instance is None:
             raise LLMInvocationError("Model instance is not initialized.")

        logger.debug(f"Invoking HuggingFace model '{self.model_name}' via LangChain {type(self._model_instance).__name__}.")

        # Adapt prompt format if necessary, especially if using HuggingFaceEndpoint directly
        if not isinstance(self._model_instance, ChatHuggingFace) and not isinstance(prompt, str):
             logger.warning(f"HuggingFaceEndpoint expects string prompt, received {type(prompt)}. Using content of first message or converting.")
             # Convert complex prompt types to string for basic LLM interface
             if isinstance(prompt, (list, ChatPromptValue)):
                 first_msg = None
                 if isinstance(prompt, ChatPromptValue) and hasattr(prompt, 'messages'):
                      first_msg = prompt.messages[0] if prompt.messages else None
                 elif isinstance(prompt, list) and prompt:
                      first_msg = prompt[0]

                 if isinstance(first_msg, BaseMessage):
                      prompt_input = first_msg.content
                 elif isinstance(first_msg, dict):
                      prompt_input = first_msg.get("content", str(first_msg))
                 else:
                      prompt_input = str(prompt) # Fallback conversion
             else:
                  prompt_input = str(prompt) # Fallback conversion
        else:
             # If it's ChatHuggingFace or prompt is already string, use as is
             prompt_input = prompt


        try:
            response = self._model_instance.invoke(prompt_input)
            logger.debug(f"Received response from HuggingFace model '{self.model_name}'. Type: {type(response)}")
            # Response might be AIMessage or str
            # Log metadata if available
            if hasattr(response, 'response_metadata') and response.response_metadata:
                 logger.trace(f"HuggingFace Response Metadata received: {response.response_metadata}")

            return response
        except Exception as e:
            logger.error(f"Error invoking HuggingFace model '{self.model_name}': {e}", exc_info=True)
            raise LLMInvocationError(f"HuggingFace API call failed for repo '{self.model_name}': {e}") from e