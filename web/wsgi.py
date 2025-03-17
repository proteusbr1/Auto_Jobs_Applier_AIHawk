"""
WSGI entry point for the Auto_Jobs_Applier_AIHawk web application.
"""
import os
from app import create_app, create_celery_app

app = create_app(os.environ.get('APP_ENV', 'default'))
celery = create_celery_app(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
