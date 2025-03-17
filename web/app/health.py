"""
Health check endpoints for the AIHawk application.
"""
import time
import psutil
import socket
from flask import Blueprint, jsonify, current_app
from sqlalchemy import text
from redis.exceptions import RedisError

from app import db
from app.extensions import redis_client

health_bp = Blueprint('health', __name__)

# Start time of the application
START_TIME = time.time()


@health_bp.route('/health')
def health_check():
    """
    Basic health check endpoint that returns the status of the application.
    """
    return jsonify({
        'status': 'ok',
        'version': current_app.config.get('VERSION', 'unknown'),
        'timestamp': int(time.time())
    })


@health_bp.route('/health/detailed')
def detailed_health_check():
    """
    Detailed health check that includes database, Redis, and system information.
    """
    # Check database connection
    db_status = 'ok'
    db_error = None
    try:
        # Execute a simple query to check database connection
        db.session.execute(text('SELECT 1'))
    except Exception as e:
        db_status = 'error'
        db_error = str(e)
    
    # Check Redis connection
    redis_status = 'ok'
    redis_error = None
    try:
        # Ping Redis to check connection
        redis_client.ping()
    except RedisError as e:
        redis_status = 'error'
        redis_error = str(e)
    except Exception:
        redis_status = 'error'
        redis_error = 'Redis client not configured'
    
    # System information
    hostname = socket.gethostname()
    uptime = int(time.time() - START_TIME)
    
    # CPU and memory usage
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    memory_percent = memory.percent
    
    # Disk usage
    disk = psutil.disk_usage('/')
    disk_percent = disk.percent
    
    return jsonify({
        'status': 'ok' if db_status == 'ok' and redis_status == 'ok' else 'degraded',
        'version': current_app.config.get('VERSION', 'unknown'),
        'timestamp': int(time.time()),
        'hostname': hostname,
        'uptime_seconds': uptime,
        'system': {
            'cpu_percent': cpu_percent,
            'memory_percent': memory_percent,
            'disk_percent': disk_percent
        },
        'services': {
            'database': {
                'status': db_status,
                'error': db_error
            },
            'redis': {
                'status': redis_status,
                'error': redis_error
            }
        }
    })


@health_bp.route('/health/readiness')
def readiness_check():
    """
    Readiness check for Kubernetes or other orchestration systems.
    Verifies that the application is ready to receive traffic.
    """
    # Check database connection
    try:
        db.session.execute(text('SELECT 1'))
    except Exception:
        return jsonify({'status': 'error', 'message': 'Database not ready'}), 503
    
    # Check Redis connection
    try:
        redis_client.ping()
    except Exception:
        return jsonify({'status': 'error', 'message': 'Redis not ready'}), 503
    
    return jsonify({'status': 'ok', 'message': 'Application is ready'})


@health_bp.route('/health/liveness')
def liveness_check():
    """
    Liveness check for Kubernetes or other orchestration systems.
    Verifies that the application is running and not deadlocked.
    """
    return jsonify({'status': 'ok', 'message': 'Application is alive'})


def init_app(app):
    """
    Register the health check blueprint with the Flask application.
    
    Args:
        app: Flask application instance
    """
    app.register_blueprint(health_bp)
