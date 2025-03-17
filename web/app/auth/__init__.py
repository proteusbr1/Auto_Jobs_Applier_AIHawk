"""
Authentication blueprint for the Auto_Jobs_Applier_AIHawk web application.
"""
from flask import Blueprint

auth_bp = Blueprint('auth', __name__)

from app.auth import routes
