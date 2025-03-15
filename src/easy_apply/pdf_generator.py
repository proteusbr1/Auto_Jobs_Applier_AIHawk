"""
Module for generating PDF documents from HTML or text content.
"""
from loguru import logger
from weasyprint import HTML
from jinja2 import Template
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Frame, Paragraph

def render_resume_html(html_template: str, summary: str) -> str:
    """
    Renders the HTML resume template by replacing the placeholder with the personalized summary.
    
    Args:
        html_template (str): The HTML template of the resume.
        summary (str): The personalized summary to be inserted into the resume.
    
    Returns:
        str: The rendered HTML with the personalized summary.
    """
    template = Template(html_template)
    rendered_html = template.render(summary=summary)
    return rendered_html

def generate_pdf_from_html(rendered_html: str, output_path: str) -> str:
    """
    Generates a PDF from the rendered HTML using WeasyPrint.
    
    Args:
        rendered_html (str): The rendered HTML content.
        output_path (str): The path where the PDF will be saved.
    
    Returns:
        str: The absolute path of the generated PDF.
    """
    try:
        # Create an HTML object from the HTML string
        html = HTML(string=rendered_html)
        
        # Generate the PDF and save to the specified path
        html.write_pdf(target=output_path)
        
        logger.debug(f"PDF generated and saved at: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error generating PDF: {e}", exc_info=True)
        raise

def generate_pdf_from_text(file_path_pdf: str, content: str, title: str) -> None:
    """
    Generates a PDF file with the specified text content.
    
    Args:
        file_path_pdf (str): The path where the PDF will be saved.
        content (str): The textual content to include in the PDF.
        title (str): The title of the PDF document.
    """
    logger.debug(f"Generating PDF for: {title}")
    try:
        c = canvas.Canvas(file_path_pdf, pagesize=A4)
        styles = getSampleStyleSheet()
        style = styles['Normal']
        style.fontName = 'Helvetica'
        style.fontSize = 12
        style.leading = 15
        style.alignment = TA_JUSTIFY

        paragraph = Paragraph(content, style)
        frame = Frame(inch, inch, A4[0] - 2 * inch, A4[1] - 2 * inch, showBoundary=0)
        frame.addFromList([paragraph], c)
        c.save()
        logger.debug(f"PDF generated and saved at: {file_path_pdf}")
    except Exception as e:
        logger.error(f"Failed to generate PDF for {title}: {e}", exc_info=True)
        raise
