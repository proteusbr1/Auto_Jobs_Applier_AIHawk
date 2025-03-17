"""
API routes for job applications in the Auto_Jobs_Applier_AIHawk web application.
"""
from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import desc

from app import db
from app.api import api_bp
from app.models import User, JobApplication, JobApplicationStatusUpdate


@api_bp.route('/job-applications', methods=['GET'])
@jwt_required()
def get_job_applications():
    """Get all job applications for the current user."""
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    
    # Get query parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')
    company = request.args.get('company')
    search_term = request.args.get('search_term')
    
    # Build query
    query = user.job_applications
    
    if status:
        query = query.filter_by(status=status)
    
    if company:
        query = query.filter(JobApplication.company_name.ilike(f'%{company}%'))
    
    if search_term:
        query = query.filter(
            (JobApplication.job_title.ilike(f'%{search_term}%')) |
            (JobApplication.company_name.ilike(f'%{search_term}%')) |
            (JobApplication.location.ilike(f'%{search_term}%'))
        )
    
    # Order by application date, newest first
    query = query.order_by(desc(JobApplication.application_date))
    
    # Paginate results
    paginated_apps = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'job_applications': [app.to_dict() for app in paginated_apps.items],
        'total': paginated_apps.total,
        'pages': paginated_apps.pages,
        'page': page,
        'per_page': per_page
    })


@api_bp.route('/job-applications/<int:application_id>', methods=['GET'])
@jwt_required()
def get_job_application(application_id):
    """Get a specific job application."""
    user_id = get_jwt_identity()
    application = JobApplication.query.filter_by(id=application_id, user_id=user_id).first_or_404()
    
    # Get detailed information including status updates
    status_updates = [
        {
            'id': update.id,
            'status': update.status,
            'notes': update.notes,
            'timestamp': update.timestamp.isoformat() if update.timestamp else None
        }
        for update in application.status_updates.order_by(desc(JobApplicationStatusUpdate.timestamp)).all()
    ]
    
    # Get application details
    app_dict = application.to_dict()
    app_dict['status_updates'] = status_updates
    app_dict['questions_and_answers'] = application.questions_and_answers
    app_dict['application_details'] = application.application_details
    app_dict['job_description'] = application.job_description
    
    return jsonify(app_dict)


@api_bp.route('/job-applications/<int:application_id>/status', methods=['PUT'])
@jwt_required()
def update_job_application_status(application_id):
    """Update a job application's status."""
    user_id = get_jwt_identity()
    application = JobApplication.query.filter_by(id=application_id, user_id=user_id).first_or_404()
    
    data = request.json
    new_status = data.get('status')
    notes = data.get('notes')
    
    if not new_status:
        return jsonify({'error': 'Status is required'}), 400
    
    # Add status update
    application.add_status_update(new_status, notes)
    
    return jsonify({
        'message': 'Job application status updated successfully',
        'application': application.to_dict()
    })


@api_bp.route('/job-applications/<int:application_id>/notes', methods=['PUT'])
@jwt_required()
def update_job_application_notes(application_id):
    """Update a job application's notes."""
    user_id = get_jwt_identity()
    application = JobApplication.query.filter_by(id=application_id, user_id=user_id).first_or_404()
    
    data = request.json
    notes = data.get('notes')
    
    if notes is None:
        return jsonify({'error': 'Notes are required'}), 400
    
    # Update application details to include notes
    app_details = application.application_details
    app_details['notes'] = notes
    application.application_details = app_details
    
    db.session.commit()
    
    return jsonify({
        'message': 'Job application notes updated successfully',
        'application': application.to_dict()
    })


@api_bp.route('/job-applications/stats', methods=['GET'])
@jwt_required()
def get_job_application_stats():
    """Get job application statistics."""
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    
    # Count applications by status
    status_counts = db.session.query(
        JobApplication.status, db.func.count(JobApplication.id)
    ).filter(
        JobApplication.user_id == user_id
    ).group_by(
        JobApplication.status
    ).all()
    
    status_stats = {status: count for status, count in status_counts}
    
    # Count applications by company
    company_counts = db.session.query(
        JobApplication.company_name, db.func.count(JobApplication.id)
    ).filter(
        JobApplication.user_id == user_id
    ).group_by(
        JobApplication.company_name
    ).order_by(
        db.func.count(JobApplication.id).desc()
    ).limit(10).all()
    
    company_stats = {company: count for company, count in company_counts}
    
    # Count applications by search term
    search_term_counts = db.session.query(
        JobApplication.search_term, db.func.count(JobApplication.id)
    ).filter(
        JobApplication.user_id == user_id,
        JobApplication.search_term.isnot(None)
    ).group_by(
        JobApplication.search_term
    ).order_by(
        db.func.count(JobApplication.id).desc()
    ).limit(10).all()
    
    search_term_stats = {term: count for term, count in search_term_counts}
    
    return jsonify({
        'total_applications': user.job_applications.count(),
        'by_status': status_stats,
        'top_companies': company_stats,
        'top_search_terms': search_term_stats
    })


@api_bp.route('/job-applications/<int:application_id>', methods=['DELETE'])
@jwt_required()
def delete_job_application(application_id):
    """Delete a job application."""
    user_id = get_jwt_identity()
    application = JobApplication.query.filter_by(id=application_id, user_id=user_id).first_or_404()
    
    db.session.delete(application)
    db.session.commit()
    
    return jsonify({'message': 'Job application deleted successfully'})
