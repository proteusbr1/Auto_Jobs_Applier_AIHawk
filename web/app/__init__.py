"""
Application factory module for the Auto_Jobs_Applier_AIHawk web application.
"""
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_jwt_extended import JWTManager
from celery import Celery

from config import config
from app.extensions import init_redis

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
jwt = JWTManager()
celery = Celery()


def create_app(config_name=None):
    """
    Application factory function.
    
    Args:
        config_name (str): The configuration to use. Defaults to the APP_ENV
            environment variable, or 'default' if not set.
    
    Returns:
        Flask: The configured Flask application.
    """
    if config_name is None:
        config_name = os.environ.get('APP_ENV', 'default')
    
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config[config_name])
    
    # Ensure the instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)
    
    # Initialize extensions with the app
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    jwt.init_app(app)
    
    # Configure Celery
    celery.conf.update(app.config)
    
    # Configure login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # Register blueprints
    try:
        from app.auth import auth_bp
        app.register_blueprint(auth_bp)
    except ImportError:
        pass
    
    try:
        from app.api import api_bp
        app.register_blueprint(api_bp, url_prefix='/api')
    except ImportError:
        pass
    
    # Register main blueprint with health check
    from app.routes import bp as health_bp
    app.register_blueprint(health_bp)
    
    # Register main blueprint with routes
    from app.main import main_bp
    app.register_blueprint(main_bp)
    
    # Register admin blueprint
    try:
        from app.admin import admin_bp
        app.register_blueprint(admin_bp)
    except ImportError:
        pass
    
    # Register LinkedIn blueprint
    try:
        from app.linkedin import init_app as init_linkedin
        init_linkedin(app)
    except ImportError:
        pass
    
    # Try to register health check blueprint
    try:
        from app.health import init_app as init_health
        init_health(app)
    except ImportError:
        pass
    
    # Initialize Redis
    init_redis(app)
    
    # Create user data directory if it doesn't exist
    user_data_dir = app.config['USER_DATA_DIR']
    os.makedirs(user_data_dir, exist_ok=True)
    
    # Register error handlers
    register_error_handlers(app)
    
    return app


def register_error_handlers(app):
    """
    Register error handlers for the application.
    
    Args:
        app (Flask): The Flask application.
    """
    @app.errorhandler(404)
    def page_not_found(e):
        return {'error': 'Not found'}, 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        return {'error': 'Internal server error'}, 500


def create_celery_app(app=None):
    """
    Create a Celery application configured from the Flask app.
    
    Args:
        app (Flask, optional): The Flask application. If not provided,
            a new application will be created.
    
    Returns:
        Celery: The configured Celery application.
    """
    app = app or create_app()
    
    class FlaskTask(celery.Task):
        """Celery task with Flask application context."""
        
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = FlaskTask
    return celery
