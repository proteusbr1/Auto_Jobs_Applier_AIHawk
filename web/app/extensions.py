"""
Extensions for the AIHawk application.
"""
import redis
from flask import current_app

# Initialize Redis client
redis_client = redis.Redis.from_url(
    url='redis://redis:6379/0',  # Default URL, will be overridden by app config
    decode_responses=True
)

def init_redis(app):
    """
    Initialize Redis client with app configuration.
    
    Args:
        app: Flask application instance
    """
    global redis_client
    redis_client = redis.Redis.from_url(
        url=app.config['REDIS_URL'],
        decode_responses=True
    )
