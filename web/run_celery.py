#!/usr/bin/env python
"""
Celery worker script for the Auto_Jobs_Applier_AIHawk web application.
"""
import os
from app import create_app, create_celery_app

app = create_app(os.environ.get('APP_ENV', 'development'))
celery = create_celery_app(app)

if __name__ == '__main__':
    # This script is used to start Celery workers
    # Run with: python web/run_celery.py worker -l info
    # Or: celery -A run_celery:celery worker -l info
    pass
