"""
Logging configuration for the AIHawk application.
"""
import os
import logging
from logging.handlers import RotatingFileHandler, SMTPHandler
import json
from pythonjsonlogger import jsonlogger

LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
LOG_DIR = os.environ.get('LOG_DIR', 'logs')
LOG_FILE_MAX_BYTES = int(os.environ.get('LOG_FILE_MAX_BYTES', 10485760))  # 10MB
LOG_FILE_BACKUP_COUNT = int(os.environ.get('LOG_FILE_BACKUP_COUNT', 10))

# Ensure log directory exists
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter for logs that adds additional fields.
    """
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        log_record['timestamp'] = self.formatTime(record)
        
        # Add trace ID if available
        if hasattr(record, 'trace_id'):
            log_record['trace_id'] = record.trace_id
        
        # Add user ID if available
        if hasattr(record, 'user_id'):
            log_record['user_id'] = record.user_id


def configure_logging(app):
    """
    Configure logging for the application.
    
    Args:
        app: Flask application instance
    """
    # Clear existing handlers
    for handler in app.logger.handlers:
        app.logger.removeHandler(handler)
    
    # Set log level
    app.logger.setLevel(getattr(logging, LOG_LEVEL))
    
    # Create formatters
    json_formatter = CustomJsonFormatter('%(timestamp)s %(level)s %(name)s %(message)s')
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(json_formatter)
    app.logger.addHandler(console_handler)
    
    # File handler for general logs
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, 'app.log'),
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT
    )
    file_handler.setFormatter(json_formatter)
    app.logger.addHandler(file_handler)
    
    # File handler for error logs
    error_file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, 'error.log'),
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(json_formatter)
    app.logger.addHandler(error_file_handler)
    
    # Email handler for critical errors in production
    if not app.debug and not app.testing:
        mail_handler = SMTPHandler(
            mailhost=(app.config['MAIL_SERVER'], app.config['MAIL_PORT']),
            fromaddr=app.config['MAIL_DEFAULT_SENDER'],
            toaddrs=app.config.get('ADMINS', []),
            subject='AIHawk Application Error',
            credentials=(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD']),
            secure=app.config['MAIL_USE_TLS']
        )
        mail_handler.setLevel(logging.ERROR)
        mail_handler.setFormatter(json_formatter)
        app.logger.addHandler(mail_handler)
    
    # Log startup message
    app.logger.info('AIHawk application starting', extra={
        'environment': app.config['ENV'],
        'debug': app.debug,
        'testing': app.testing
    })
    
    return app.logger


class RequestLogger:
    """
    Middleware for logging HTTP requests.
    """
    def __init__(self, app):
        self.app = app
        self.logger = app.logger
    
    def __call__(self, environ, start_response):
        # Log request
        request_id = environ.get('HTTP_X_REQUEST_ID', '-')
        method = environ.get('REQUEST_METHOD', '-')
        path = environ.get('PATH_INFO', '-')
        query = environ.get('QUERY_STRING', '')
        remote_addr = environ.get('REMOTE_ADDR', '-')
        user_agent = environ.get('HTTP_USER_AGENT', '-')
        
        if query:
            path = f"{path}?{query}"
        
        self.logger.info(f"Request: {method} {path}", extra={
            'request_id': request_id,
            'method': method,
            'path': path,
            'remote_addr': remote_addr,
            'user_agent': user_agent
        })
        
        # Capture response
        def custom_start_response(status, headers, exc_info=None):
            status_code = int(status.split(' ')[0])
            self.logger.info(f"Response: {status}", extra={
                'request_id': request_id,
                'method': method,
                'path': path,
                'status_code': status_code
            })
            return start_response(status, headers, exc_info)
        
        return self.app(environ, custom_start_response)


def init_app(app):
    """
    Initialize logging for the application.
    
    Args:
        app: Flask application instance
    
    Returns:
        The configured Flask application
    """
    configure_logging(app)
    
    # Add request logging middleware
    if not app.debug and not app.testing:
        app.wsgi_app = RequestLogger(app.wsgi_app)
    
    return app
