"""
API routes for resume management in the Auto_Jobs_Applier_AIHawk web application.
"""
import os
from pathlib import Path
from flask import jsonify, request, current_app, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename

from app import db
from app.api import api_bp
from app.models import User, Resume, GeneratedResume, SubscriptionPlan


def allowed_file(filename):
    """Check if a file has an allowed extension."""
    allowed_extensions = {'pdf', 'docx', 'html'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


@api_bp.route('/resumes', methods=['GET'])
@jwt_required()
def get_resumes():
    """Get all resumes for the current user."""
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    
    resumes = user.resumes.filter_by(is_active=True).all()
    return jsonify({
        'resumes': [resume.to_dict() for resume in resumes]
    })


@api_bp.route('/resumes/<int:resume_id>', methods=['GET'])
@jwt_required()
def get_resume(resume_id):
    """Get a specific resume."""
    user_id = get_jwt_identity()
    resume = Resume.query.filter_by(id=resume_id, user_id=user_id).first_or_404()
    
    return jsonify(resume.to_dict())


@api_bp.route('/resumes/<int:resume_id>/download', methods=['GET'])
@jwt_required()
def download_resume(resume_id):
    """Download a resume file."""
    user_id = get_jwt_identity()
    resume = Resume.query.filter_by(id=resume_id, user_id=user_id).first_or_404()
    
    file_path = resume.get_absolute_path()
    if not os.path.exists(file_path):
        return jsonify({'error': 'Resume file not found'}), 404
    
    return send_file(file_path, as_attachment=True, download_name=f"{resume.name}.{resume.file_type}")


@api_bp.route('/resumes', methods=['POST'])
@jwt_required()
def upload_resume():
    """Upload a new resume."""
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    
    # Check if user has reached the maximum number of resumes
    subscription = user.subscription
    if subscription and subscription.is_active():
        # Get the subscription plan
        plan = SubscriptionPlan.query.filter_by(name=subscription.plan).first()
        if plan and plan.features:
            import json
            try:
                features = json.loads(plan.features)
                max_resumes = features.get('max_resumes')
                if max_resumes and user.resumes.count() >= int(max_resumes):
                    return jsonify({
                        'error': f'You have reached the maximum number of resumes ({max_resumes}) allowed by your subscription plan.'
                    }), 403
            except (json.JSONDecodeError, ValueError) as e:
                current_app.logger.error(f"Error parsing subscription plan features: {e}")
    
    # Check if the post request has the file part
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    
    # If user does not select file, browser also
    # submit an empty part without filename
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400
    
    # Get form data
    name = request.form.get('name', 'Resume')
    description = request.form.get('description', '')
    is_default = request.form.get('is_default', 'false').lower() == 'true'
    
    # Create user directory if it doesn't exist
    user_data_dir = current_app.config['USER_DATA_DIR']
    user_resume_dir = Path(user_data_dir, str(user_id), 'resumes')
    os.makedirs(user_resume_dir, exist_ok=True)
    
    # Save the file
    filename = secure_filename(file.filename)
    file_type = filename.rsplit('.', 1)[1].lower()
    file_path = Path(user_resume_dir, filename)
    file.save(file_path)
    
    # Extract plain text content (simplified for now)
    plain_text_content = None
    
    # Create resume record
    resume = Resume(
        user_id=user_id,
        name=name,
        description=description,
        file_path=filename,
        file_type=file_type,
        is_default=is_default,
        plain_text_content=plain_text_content
    )
    
    # If this is the default resume, unset default flag on other resumes
    if is_default:
        for other_resume in user.resumes:
            if other_resume.is_default:
                other_resume.is_default = False
    
    db.session.add(resume)
    db.session.commit()
    
    return jsonify(resume.to_dict()), 201


@api_bp.route('/resumes/<int:resume_id>', methods=['PUT'])
@jwt_required()
def update_resume(resume_id):
    """Update a resume's metadata."""
    user_id = get_jwt_identity()
    resume = Resume.query.filter_by(id=resume_id, user_id=user_id).first_or_404()
    
    data = request.json
    
    if 'name' in data:
        resume.name = data['name']
    
    if 'description' in data:
        resume.description = data['description']
    
    if 'is_default' in data and data['is_default']:
        # Unset default flag on other resumes
        for other_resume in Resume.query.filter(
            Resume.user_id == user_id,
            Resume.id != resume_id,
            Resume.is_default == True
        ).all():
            other_resume.is_default = False
        
        resume.is_default = True
    
    db.session.commit()
    
    return jsonify(resume.to_dict())


@api_bp.route('/resumes/<int:resume_id>', methods=['DELETE'])
@jwt_required()
def delete_resume(resume_id):
    """Delete a resume."""
    user_id = get_jwt_identity()
    resume = Resume.query.filter_by(id=resume_id, user_id=user_id).first_or_404()
    
    # Delete the file
    resume.delete_file()
    
    # Delete the database record
    db.session.delete(resume)
    db.session.commit()
    
    return jsonify({'message': 'Resume deleted successfully'})


@api_bp.route('/resumes/<int:resume_id>/set-default', methods=['POST'])
@jwt_required()
def set_default_resume(resume_id):
    """Set a resume as the default."""
    user_id = get_jwt_identity()
    resume = Resume.query.filter_by(id=resume_id, user_id=user_id).first_or_404()
    
    # Unset default flag on other resumes
    for other_resume in Resume.query.filter(
        Resume.user_id == user_id,
        Resume.id != resume_id,
        Resume.is_default == True
    ).all():
        other_resume.is_default = False
    
    resume.is_default = True
    db.session.commit()
    
    return jsonify({'message': 'Default resume set successfully'})


@api_bp.route('/generated-resumes', methods=['GET'])
@jwt_required()
def get_generated_resumes():
    """Get all generated resumes for the current user."""
    user_id = get_jwt_identity()
    
    generated_resumes = GeneratedResume.query.filter_by(user_id=user_id).all()
    return jsonify({
        'generated_resumes': [resume.to_dict() for resume in generated_resumes]
    })


@api_bp.route('/generated-resumes/<int:resume_id>', methods=['GET'])
@jwt_required()
def get_generated_resume(resume_id):
    """Get a specific generated resume."""
    user_id = get_jwt_identity()
    resume = GeneratedResume.query.filter_by(id=resume_id, user_id=user_id).first_or_404()
    
    return jsonify(resume.to_dict())


@api_bp.route('/generated-resumes/<int:resume_id>/download', methods=['GET'])
@jwt_required()
def download_generated_resume(resume_id):
    """Download a generated resume file."""
    user_id = get_jwt_identity()
    resume = GeneratedResume.query.filter_by(id=resume_id, user_id=user_id).first_or_404()
    
    file_path = resume.get_absolute_path()
    if not os.path.exists(file_path):
        return jsonify({'error': 'Generated resume file not found'}), 404
    
    return send_file(file_path, as_attachment=True, download_name=f"{resume.job_title}_{resume.company_name}.{resume.file_type}")


@api_bp.route('/generated-resumes/<int:resume_id>', methods=['DELETE'])
@jwt_required()
def delete_generated_resume(resume_id):
    """Delete a generated resume."""
    user_id = get_jwt_identity()
    resume = GeneratedResume.query.filter_by(id=resume_id, user_id=user_id).first_or_404()
    
    # Delete the file
    resume.delete_file()
    
    # Delete the database record
    db.session.delete(resume)
    db.session.commit()
    
    return jsonify({'message': 'Generated resume deleted successfully'})
