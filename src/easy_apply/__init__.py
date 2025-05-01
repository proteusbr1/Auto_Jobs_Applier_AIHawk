# src/easy_apply/__init__.py
"""
Easy Apply package for handling specific website automation flows,
primarily focused on job application forms (like LinkedIn Easy Apply).
"""

# Export the main handler class
from .applier import EasyApplyHandler

# Optionally export other components if used directly elsewhere
# from .form_handler import FormHandler
# from .file_uploader import FileUploader
# from .answer_storage import AnswerStorage
# ... etc.

__all__ = [
    'EasyApplyHandler',
    # Add other exported classes here if needed
]