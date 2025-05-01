# src/easy_apply/pdf_generator.py
"""
Generates PDF documents from HTML templates or plain text content.
Uses WeasyPrint for HTML-to-PDF and ReportLab for text-to-PDF.
"""
from pathlib import Path
from loguru import logger
from typing import Optional


# PDF Generation Libraries
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    logger.warning("WeasyPrint not found. HTML to PDF generation will not be available.")
    WEASYPRINT_AVAILABLE = False
    HTML = None # Define HTML as None if not available

try:
    from jinja2 import Template
    JINJA2_AVAILABLE = True
except ImportError:
     logger.warning("Jinja2 not found. HTML templating will not be available.")
     JINJA2_AVAILABLE = False
     Template = None # Define Template as None

try:
    from reportlab.lib.enums import TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Frame, Paragraph, Spacer
    REPORTLAB_AVAILABLE = True
except ImportError:
     logger.warning("ReportLab not found. Text to PDF generation will not be available.")
     REPORTLAB_AVAILABLE = False
     # Define placeholders if needed


def render_resume_html(html_template_content: str, summary: str) -> Optional[str]:
    """
    Renders an HTML resume template using Jinja2, inserting a personalized summary.

    Args:
        html_template_content (str): The raw HTML template string.
        summary (str): The personalized summary text to insert.

    Returns:
        Optional[str]: The rendered HTML string, or None if Jinja2 is unavailable or rendering fails.
    """
    if not JINJA2_AVAILABLE:
        logger.error("Jinja2 library is required for HTML templating but not installed.")
        return None
    if not Template: # Check if Template is defined
         logger.error("Jinja2 Template class not available.")
         return None

    try:
        template = Template(html_template_content)
        # Assuming the template uses a variable named 'summary'
        rendered_html = template.render(summary=summary)
        logger.debug("HTML template rendered successfully.")
        return rendered_html
    except Exception as e:
        logger.error(f"Error rendering HTML template with Jinja2: {e}", exc_info=True)
        return None

def generate_pdf_from_html(html_content: str, output_path: Path) -> bool:
    """
    Generates a PDF file from HTML content using WeasyPrint.

    Args:
        html_content (str): The HTML content string.
        output_path (Path): The Path object where the PDF file will be saved.

    Returns:
        bool: True if PDF generation was successful, False otherwise.
    """
    if not WEASYPRINT_AVAILABLE:
        logger.error("WeasyPrint library is required for HTML-to-PDF generation but not installed.")
        return False
    if not HTML: # Check if HTML class is defined
         logger.error("WeasyPrint HTML class not available.")
         return False

    try:
        logger.debug(f"Generating PDF from HTML to: {output_path}")
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        html_obj = HTML(string=html_content)
        html_obj.write_pdf(target=str(output_path)) # write_pdf expects string path or file object

        logger.info(f"PDF successfully generated from HTML: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Error generating PDF from HTML using WeasyPrint: {e}", exc_info=True)
        # Attempt to delete potentially corrupt partial file
        if output_path.exists():
             try: output_path.unlink()
             except OSError: pass
        return False


def generate_pdf_from_text(output_path: Path, content: str, title: str) -> bool:
    """
    Generates a simple PDF file containing the provided text using ReportLab.

    Args:
        output_path (Path): The Path object where the PDF file will be saved.
        content (str): The plain text content to include in the PDF.
        title (str): The title for the PDF document metadata.

    Returns:
        bool: True if PDF generation was successful, False otherwise.
    """
    if not REPORTLAB_AVAILABLE:
         logger.error("ReportLab library is required for text-to-PDF generation but not installed.")
         return False

    logger.debug(f"Generating PDF from text for '{title}' to: {output_path}")
    try:
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        pdf_canvas = canvas.Canvas(str(output_path), pagesize=A4)
        pdf_canvas.setTitle(title)

        # Define styles
        styles = getSampleStyleSheet()
        # Customize normal style for better readability
        normal_style = ParagraphStyle(
            name='Normal_Justified',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=11,
            leading=14, # Line spacing
            alignment=TA_JUSTIFY,
            spaceAfter=6 # Space after paragraph
        )

        # Prepare content - replace newlines for ReportLab Paragraphs
        formatted_content = content.replace('\n', '<br/>')
        story = [Paragraph(formatted_content, normal_style)]

        # Define layout frame (margins)
        margin = 1 * inch
        frame_width = A4[0] - 2 * margin
        frame_height = A4[1] - 2 * margin
        frame = Frame(margin, margin, frame_width, frame_height, id='normal')

        # Build the story within the frame
        frame.addFromList(story, pdf_canvas)
        pdf_canvas.save()

        logger.info(f"PDF successfully generated from text: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Error generating PDF from text using ReportLab: {e}", exc_info=True)
        # Attempt to delete potentially corrupt partial file
        if output_path.exists():
             try: output_path.unlink()
             except OSError: pass
        return False