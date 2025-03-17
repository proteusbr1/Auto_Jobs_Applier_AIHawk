"""
API authentication routes for the Auto_Jobs_Applier_AIHawk web application.
"""
from datetime import datetime, timezone
from flask import jsonify, request
from flask_jwt_extended import (
    create_access_token, create_refresh_token, jwt_required,
    get_jwt_identity, get_jwt
)

from app import db, jwt
from app.api import api_bp
from app.models import User


# JWT token blocklist (in-memory for simplicity, would use Redis in production)
jwt_blocklist = set()


@jwt.token_in_blocklist_loader
def check_if_token_in_blocklist(jwt_header, jwt_payload):
    """Check if a token is in the blocklist."""
    jti = jwt_payload["jti"]
    return jti in jwt_blocklist


@api_bp.route('/auth/login', methods=['POST'])
def login():
    """API login endpoint."""
    if not request.is_json:
        return jsonify({"error": "Missing JSON in request"}), 400
    
    email = request.json.get('email', None)
    password = request.json.get('password', None)
    
    if not email or not password:
        return jsonify({"error": "Missing email or password"}), 400
    
    user = User.query.filter_by(email=email.lower()).first()
    
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password"}), 401
    
    if not user.is_active:
        return jsonify({"error": "Account is disabled"}), 401
    
    # Update last login time
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()
    
    # Create tokens
    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)
    
    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_admin": user.is_admin
        }
    })


@api_bp.route('/auth/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token."""
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    if not user or not user.is_active:
        return jsonify({"error": "User not found or inactive"}), 401
    
    access_token = create_access_token(identity=current_user_id)
    return jsonify({"access_token": access_token})


@api_bp.route('/auth/logout', methods=['POST'])
@jwt_required()
def logout():
    """Logout and revoke tokens."""
    jti = get_jwt()["jti"]
    jwt_blocklist.add(jti)
    return jsonify({"message": "Successfully logged out"})


@api_bp.route('/auth/register', methods=['POST'])
def register():
    """API registration endpoint."""
    if not request.is_json:
        return jsonify({"error": "Missing JSON in request"}), 400
    
    data = request.json
    required_fields = ['username', 'email', 'password']
    
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({"error": f"Missing {field}"}), 400
    
    # Check if username or email already exists
    if User.query.filter_by(username=data['username']).first():
        return jsonify({"error": "Username already exists"}), 400
    
    if User.query.filter_by(email=data['email'].lower()).first():
        return jsonify({"error": "Email already exists"}), 400
    
    # Create new user
    user = User(
        username=data['username'],
        email=data['email'].lower(),
        password=data['password'],
        first_name=data.get('first_name'),
        last_name=data.get('last_name')
    )
    
    db.session.add(user)
    db.session.commit()
    
    return jsonify({
        "message": "User registered successfully",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email
        }
    }), 201
