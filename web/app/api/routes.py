"""
General API routes for the Auto_Jobs_Applier_AIHawk web application.
"""
from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.api import api_bp
from app.models import User


@api_bp.route('/status', methods=['GET'])
def status():
    """API status endpoint."""
    return jsonify({
        'app_name': 'Auto_Jobs_Applier_AIHawk',
        'status': 'online',
        'version': '1.0.0'
    })


@api_bp.route('/user', methods=['GET'])
@jwt_required()
def get_user():
    """Get current user information."""
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    
    return jsonify(user.to_dict())


@api_bp.route('/check-auth', methods=['GET'])
def check_auth():
    """Check if the user is authenticated."""
    auth_header = request.headers.get('Authorization', '')
    has_token = auth_header.startswith('Bearer ')
    
    if not has_token:
        return jsonify({
            'authenticated': False,
            'message': 'No token provided'
        })
    
    token = auth_header[7:]
    
    try:
        # This will verify the token and raise an exception if invalid
        from flask_jwt_extended import decode_token
        decoded = decode_token(token)
        user_id = decoded['sub']
        
        # Check if user exists
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'authenticated': False,
                'message': 'User not found'
            })
        
        if not user.is_active:
            return jsonify({
                'authenticated': False,
                'message': 'User is inactive'
            })
        
        return jsonify({
            'authenticated': True,
            'user_id': user_id,
            'user_email': user.email
        })
    except Exception as e:
        return jsonify({
            'authenticated': False,
            'message': str(e)
        })
