"""
Routes for the AIHawk web application.
"""
from flask import Blueprint, jsonify

bp = Blueprint('basic_health', __name__)

@bp.route('/health')
def health():
    """
    Health check endpoint.
    """
    return jsonify({'status': 'ok'})
