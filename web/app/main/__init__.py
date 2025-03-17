"""
Main blueprint for the Auto_Jobs_Applier_AIHawk web application.
"""
from flask import Blueprint

main_bp = Blueprint('main', __name__)

from app.main import routes
