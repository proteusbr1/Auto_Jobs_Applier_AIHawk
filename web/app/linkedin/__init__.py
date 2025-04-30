"""
LinkedIn blueprint for AIHawk.

This blueprint handles LinkedIn integration, including authentication and job search.
"""
from flask import Blueprint

# Create the LinkedIn blueprint
linkedin_bp = Blueprint('linkedin', __name__, url_prefix='/linkedin')

# Import routes
from app.linkedin.auth import init_linkedin_auth_routes

def init_app(app):
    """Initialize the LinkedIn blueprint with the Flask app.
    
    Args:
        app (Flask): The Flask application.
    """
    # Initialize routes before registering the blueprint
    init_linkedin_auth_routes(app)
    
    # Register the blueprint
    app.register_blueprint(linkedin_bp)
