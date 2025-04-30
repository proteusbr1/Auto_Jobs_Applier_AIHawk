"""
Implementation of the AIModel interface for Google Gemini models.
"""

from loguru import logger
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAI
from src.llm.models.base_model import AIModel
from typing import List, Dict, Union, Any


class GeminiModel(AIModel):
    """
    Implementation of the AIModel interface for Google Gemini models.
    Uses the langchain-google-genai library.
    """

    def __init__(self, api_key: str, llm_model: str):
        """
        Initialize the GeminiModel with the specified API key and model name.

        Args:
            api_key (str): The API key for Google Gemini (GOOGLE_API_KEY).
            llm_model (str): The name of the Gemini model to use (e.g., 'gemini-1.5-flash').
        """
        self.model_name = llm_model
        
        # Map model names to their API-compatible variants with pricing versions
        model_mapping = {
            "gemini-2.5-flash-preview": "gemini-2.5-flash-preview-04-17",
            # Add other mappings as needed
        }
        
        # Use the mapped version if available, otherwise use the original
        api_model_name = model_mapping.get(llm_model, llm_model)
        
        try:
            # Create the model instance using LangChain's ChatGoogleGenerativeAI
            self.model = ChatGoogleGenerativeAI(
                model=api_model_name,
                google_api_key=api_key,
                temperature=0.7,
                convert_system_message_to_human=True
            )
            
            # Store the model name used for pricing lookup - ensure it matches one of the keys in MODEL_PRICING
            # Check if the model name exists in the pricing dictionary
            from src.llm.utils.pricing import MODEL_PRICING
            
            # Try to find an exact match in the pricing dictionary
            if llm_model in MODEL_PRICING:
                self.pricing_model_name = llm_model
            # If using a mapped model name, check if that's in the pricing dictionary
            elif api_model_name in MODEL_PRICING:
                self.pricing_model_name = api_model_name
            # Fall back to a more generic version if available
            elif llm_model.startswith("gemini-1.5-flash"):
                self.pricing_model_name = "gemini-1.5-flash"
            elif llm_model.startswith("gemini-2.5-flash"):
                self.pricing_model_name = "gemini-2.5-flash-preview-04-17"
            elif llm_model.startswith("gemini-1.5-pro"):
                self.pricing_model_name = "gemini-1.5-pro"
            elif llm_model.startswith("gemini-2.5-pro"):
                self.pricing_model_name = "gemini-2.5-pro-preview"
            else:
                # If no match found, use the original model name
                self.pricing_model_name = llm_model
            
            logger.debug(f"Using pricing model name: {self.pricing_model_name} for model: {self.model_name}")
            
            logger.debug(f"GeminiModel initialized with model: {self.model_name}, API model: {api_model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client or model: {e}")
            raise

    def invoke(self, prompt: Union[str, List[Dict[str, str]]]) -> str:
        """
        Invoke the Gemini API with the given prompt.

        Args:
            prompt (Union[str, List[Dict[str, str]]]): The input prompt for the Gemini model.
                Can be a string or a list of message dictionaries for chat models.

        Returns:
            str: The text response from the Gemini API.

        Raises:
            Exception: If an error occurs while invoking the API.
        """
        logger.debug(f"Invoking Gemini API with model {self.model_name}.")
        try:
            # Handle both string prompts and chat message lists
            if isinstance(prompt, str):
                # For string prompts, use direct invocation
                response = self.model.invoke(prompt)
                logger.debug("Gemini API invoked successfully with string prompt.")
            else:
                # For chat message lists, format properly for LangChain
                response = self.model.invoke(prompt)
                logger.debug("Gemini API invoked successfully with chat messages.")

            # Extract the content from the AIMessage response
            if hasattr(response, 'content'):
                content = response.content
                if not isinstance(content, str):
                    logger.warning(f"Expected string content from Gemini, but got {type(content)}. Converting to string.")
                    content = str(content)
                return content
            else:
                # Handle unexpected response format
                logger.warning(f"Gemini response did not contain expected content attribute. Response: {response}")
                return str(response) if response else ""

        except Exception as e:
            logger.error(f"Error invoking Gemini API: {e}")
            # Log specific details if available
            if hasattr(e, 'message'):
                logger.error(f"Gemini API Error Message: {e.message}")
            raise
