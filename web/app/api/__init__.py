"""
API blueprint for the Auto_Jobs_Applier_AIHawk web application.
"""
from flask import Blueprint

api_bp = Blueprint('api', __name__)

from app.api import routes, auth, job_configs, resumes, job_applications, job_tasks
