# src/resume_manager.py
from pathlib import Path
import re
from loguru import logger
from typing import Optional, Tuple
import yaml


class ResumeNotFoundError(FileNotFoundError):
    """Custom exception raised when the resume file is not found."""
    pass


class ResumeManager:
    """
    Handles loading and validation of the resume.

    Attributes:
        resume_path (Optional[Path]): Path to the user-provided resume file.
        default_html_resume (Path): Path to the default HTML resume file.
        resume_content (Optional[Path]): Path to the loaded resume file.
    """

    def __init__(self, default_html_resume: Path,
                 private_context_path: Optional[Path] = None):
        """
        Initializes the ResumeManager with the HTML resume path.

        Args:
            default_html_resume (Path): Path to the HTML resume file.

        Raises:
            ResumeNotFoundError: If the HTML resume does not exist.
        """
        self.html_resume_path = default_html_resume
        self.resume_content: Optional[Path] = None
        self.plain_text_content: Optional[str] = None
        self.private_context: dict = {}
        self._load_private_context(private_context_path)
        self.load_resume()

    def _extract_text_from_html(self, html_content: str) -> str:
        """
        Extracts plain text from HTML content, focusing on the body content and ignoring style/script sections.
        
        This implementation extracts only the content from the body tag and removes HTML tags,
        ignoring style and script sections.
        
        Args:
            html_content (str): The HTML content of the resume.
            
        Returns:
            str: Plain text extracted from the HTML content.
        """
        # First, extract just the body content to avoid getting CSS/JS
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html_content, re.DOTALL)
        if body_match:
            body_content = body_match.group(1)
        else:
            # Fallback to full content if no body tag found
            body_content = html_content
            
        # Remove script and style sections completely
        body_content = re.sub(r'<style[^>]*>.*?</style>', '', body_content, flags=re.DOTALL)
        body_content = re.sub(r'<script[^>]*>.*?</script>', '', body_content, flags=re.DOTALL)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', body_content)
        # Replace multiple spaces with single space
        text = re.sub(r'\s+', ' ', text)
        # Decode HTML entities (e.g., &nbsp;, &amp;)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        
        return text.strip()
    
    def _load_private_context(self, path: Optional[Path]):
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.private_context = yaml.safe_load(f) or {}
            logger.info(f"Loaded private context: {list(self.private_context.keys())}")
        except Exception as e:
            logger.warning(f"Could not load private context YAML: {e}")
    
    def load_resume(self):
        """
        Loads the HTML resume file and extracts its plain text content.

        Raises:
            ResumeNotFoundError: If the HTML resume file does not exist.
        """
        logger.info(f"Loading HTML resume from: {self.html_resume_path}")
        if self.html_resume_path.exists() and self.html_resume_path.is_file():
            self.resume_content = self.html_resume_path
            
            # Extract plain text from the HTML file
            try:
                with open(self.resume_content, 'r', encoding='utf-8') as file:
                    html_content = file.read()
                self.plain_text_content = self._extract_text_from_html(html_content)
                logger.info(f"Successfully extracted plain text from HTML resume. Length: {len(self.plain_text_content)} characters")
            except Exception as e:
                logger.error(f"Error extracting text from HTML resume: {e}")
                raise ResumeNotFoundError(f"Failed to extract text from HTML resume: {e}")
                
            logger.info(f"Successfully loaded HTML resume from: {self.resume_content}")
        else:
            logger.error(f"HTML resume file not found at: {self.html_resume_path}")
            raise ResumeNotFoundError(f"HTML resume file not found: {self.html_resume_path}")

    def get_resume(self) -> Path:
        """
        Returns the path to the loaded resume.

        Returns:
            Path: Path to the loaded resume file.

        Raises:
            ResumeNotFoundError: If the resume has not been loaded.
        """
        if self.resume_content:
            logger.debug(f"Retrieving resume path: {self.resume_content}")
            return self.resume_content
        else:
            logger.error("Attempted to retrieve resume before loading it.")
            raise ResumeNotFoundError("Resume has not been loaded.")
        
            
    def get_plain_text_content(self) -> str:
        """
        Devolve currículo *já* combinado com o contexto privado.
        """
        if not self.plain_text_content:
            logger.error("Plain-text resume ainda não carregado.")
            raise ResumeNotFoundError("Resume plain text content not available.")

        private_block = self._format_private_context()
        if private_block:
            return f"{self.plain_text_content}\n\n---\n### Informações adicionais\n{private_block}"
        return self.plain_text_content
    
            
    def get_html_and_text(self) -> Tuple[Path, str]:
        """
        Returns both the path to the HTML resume file and its extracted plain text.
        
        Returns:
            Tuple[Path, str]: A tuple containing the path to the HTML file and the extracted plain text.
            
        Raises:
            ResumeNotFoundError: If the resume has not been loaded.
        """
        if self.resume_content and self.plain_text_content:
            return self.resume_content, self.plain_text_content
        else:
            logger.error("Attempted to retrieve resume data before loading it.")
            raise ResumeNotFoundError("Resume data not available.")

    def _format_private_context(self) -> str:
        """
        Converte o dicionário private_context num bloco de texto
        legível pela LLM.
        """
        if not self.private_context:
            return ""

        lines = []
        for key, value in self.private_context.items():
            # Se o valor for lista, transforma em string “• item1, item2”
            if isinstance(value, (list, tuple, set)):
                value = ", ".join(map(str, value))
            # Chave para título amigável
            pretty_key = key.replace("_", " ").capitalize()
            lines.append(f"{pretty_key}: {value}")
        return "\n".join(lines)
