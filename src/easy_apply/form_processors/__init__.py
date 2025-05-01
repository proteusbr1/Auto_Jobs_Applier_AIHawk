# src/easy_apply/form_processors/__init__.py
"""
Form Processors Package.

This package contains modules responsible for handling specific types of form
fields encountered during the automated job application process (e.g., textboxes,
dropdowns, checkboxes) primarily within the LinkedIn Easy Apply workflow.

It defines a base processor class with shared utilities and specific implementations
for each field type. The `FormProcessorManager` orchestrates the selection and
execution of the appropriate processor for a given form section.
"""

from .processor_manager import FormProcessorManager
from .base_processor import BaseProcessor # Optional: if base class is needed elsewhere

__all__ = [
    'FormProcessorManager',
    'BaseProcessor', # Export if needed directly by other modules
]

# Individual processors are typically used only by the manager,
# so they are not included in __all__ by default.