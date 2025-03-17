"""
Main API routes for the Auto_Jobs_Applier_AIHawk web application.
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
        'status': 'online',
        'version': '1.0.0',
        'app_name': 'Auto_Jobs_Applier_AIHawk'
    })


@api_bp.route('/user', methods=['GET'])
@jwt_required()
def get_user():
    """Get current user information."""
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    
    subscription = user.subscription
    subscription_data = None
    
    if subscription:
        subscription_data = {
            'plan_name': subscription.plan.name if subscription.plan else None,
            'status': subscription.status,
            'is_trial': subscription.is_trial,
            'days_remaining': subscription.days_remaining(),
            'is_active': subscription.is_active()
        }
    
    return jsonify({
        'id': user.id,
        'username': user.email,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': user.get_full_name(),
        'is_admin': user.is_admin,
        'last_login': user.last_login.isoformat() if user.last_login else None,
        'created_at': user.created_at.isoformat() if user.created_at else None,
        'subscription': subscription_data
    })


@api_bp.route('/user', methods=['PATCH'])
@jwt_required()
def update_user():
    """Update user information."""
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    
    data = request.json
    allowed_fields = ['first_name', 'last_name']
    
    for field in allowed_fields:
        if field in data:
            setattr(user, field, data[field])
    
    db.session.commit()
    
    return jsonify({
        'message': 'User updated successfully',
        'user': {
            'id': user.id,
            'username': user.email,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'full_name': user.get_full_name()
        }
    })


@api_bp.route('/user/change-password', methods=['POST'])
@jwt_required()
def change_password():
    """Change user password."""
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    
    data = request.json
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    if not current_password or not new_password:
        return jsonify({'error': 'Current password and new password are required'}), 400
    
    if not user.check_password(current_password):
        return jsonify({'error': 'Current password is incorrect'}), 400
    
    user.set_password(new_password)
    db.session.commit()
    
    return jsonify({'message': 'Password changed successfully'})


@api_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_stats():
    """Get user statistics."""
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    
    # Count job applications by status
    applications_by_status = {}
    for app in user.job_applications:
        status = app.status
        applications_by_status[status] = applications_by_status.get(status, 0) + 1
    
    # Count applications by day for the last 30 days
    # (This would be implemented with a more complex query)
    applications_by_day = {}
    
    return jsonify({
        'total_applications': user.job_applications.count(),
        'applications_by_status': applications_by_status,
        'applications_by_day': applications_by_day,
        'total_resumes': user.resumes.count(),
        'total_job_configs': user.job_configs.count()
    })
