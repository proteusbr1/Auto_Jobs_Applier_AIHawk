"""
Authentication debugging routes for the Auto_Jobs_Applier_AIHawk web application.
"""
import os
import sys
import platform
import datetime
from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app import db, jwt
from app.api import api_bp
from app.models import User


@api_bp.route('/auth/debug', methods=['GET'])
def auth_debug():
    """
    Debug endpoint for authentication issues.
    Returns information about the current authentication state.
    """
    # Get authorization header
    auth_header = request.headers.get('Authorization', '')
    
    # Check if there's a token
    has_token = auth_header.startswith('Bearer ')
    token = auth_header[7:] if has_token else None
    
    # Get environment info
    env_info = {
        'python_version': sys.version,
        'platform': platform.platform(),
        'timestamp': datetime.datetime.now().isoformat(),
        'app_env': os.environ.get('FLASK_ENV', 'unknown'),
        'debug_mode': current_app.debug,
        'jwt_config': {
            'access_expires': str(current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES', 'unknown')),
            'refresh_expires': str(current_app.config.get('JWT_REFRESH_TOKEN_EXPIRES', 'unknown')),
            'cookie_secure': current_app.config.get('JWT_COOKIE_SECURE', 'unknown'),
            'csrf_protect': current_app.config.get('JWT_CSRF_PROTECT', 'unknown'),
        }
    }
    
    # Try to decode token if present
    token_info = {}
    user_info = {}
    
    if has_token:
        try:
            # This will verify the token and raise an exception if invalid
            user_id = get_jwt_identity()
            claims = get_jwt()
            
            token_info = {
                'valid': True,
                'user_id': user_id,
                'exp': claims.get('exp'),
                'iat': claims.get('iat'),
                'type': claims.get('type'),
                'fresh': claims.get('fresh', False),
                'expires_at': datetime.datetime.fromtimestamp(claims.get('exp')).isoformat() if claims.get('exp') else None,
                'expires_in_seconds': claims.get('exp') - datetime.datetime.now().timestamp() if claims.get('exp') else None
            }
            
            # Get user info
            user = User.query.get(user_id)
            if user:
                user_info = {
                    'id': user.id,
                    'email': user.email,
                    'is_active': user.is_active,
                    'is_admin': user.is_admin,
                    'has_subscription': user.has_active_subscription() if hasattr(user, 'has_active_subscription') else None,
                    'subscription_plan': user.get_subscription_plan() if hasattr(user, 'get_subscription_plan') else None
                }
        except Exception as e:
            token_info = {
                'valid': False,
                'error': str(e),
                'error_type': type(e).__name__
            }
    
    return jsonify({
        'auth_header_present': bool(auth_header),
        'has_token': has_token,
        'token_info': token_info,
        'user_info': user_info,
        'env_info': env_info,
        'request_info': {
            'method': request.method,
            'path': request.path,
            'remote_addr': request.remote_addr,
            'user_agent': request.user_agent.string,
            'content_type': request.content_type,
            'headers': {k: v for k, v in request.headers.items() if k.lower() not in ('authorization', 'cookie')}
        }
    })


@api_bp.route('/auth/debug/protected', methods=['GET'])
@jwt_required()
def auth_debug_protected():
    """
    Protected debug endpoint for authentication issues.
    This endpoint requires a valid JWT token.
    """
    user_id = get_jwt_identity()
    claims = get_jwt()
    
    return jsonify({
        'authenticated': True,
        'user_id': user_id,
        'jwt_claims': claims,
        'timestamp': datetime.datetime.now().isoformat()
    })
