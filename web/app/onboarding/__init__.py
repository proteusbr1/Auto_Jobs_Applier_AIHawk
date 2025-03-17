"""
Onboarding blueprint for the AIHawk application.
"""
from flask import Blueprint

onboarding_bp = Blueprint('onboarding', __name__, url_prefix='/onboarding')

from . import routes
