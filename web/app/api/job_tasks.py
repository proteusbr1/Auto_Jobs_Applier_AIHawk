"""
API routes for job tasks in the Auto_Jobs_Applier_AIHawk web application.
"""
from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from celery.result import AsyncResult

from app import db, celery
from app.api import api_bp
from app.models import User, JobConfig, Resume, JobApplication
from app.job_engine.tasks import apply_to_jobs, search_jobs, generate_resume


@api_bp.route('/job-tasks/apply', methods=['POST'])
@jwt_required()
def start_job_application():
    """Start a job application task."""
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    
    data = request.json or {}
    job_config_id = data.get('job_config_id')
    resume_id = data.get('resume_id')
    
    # Validate job config
    if job_config_id:
        job_config = JobConfig.query.filter_by(id=job_config_id, user_id=user_id).first()
        if not job_config:
            return jsonify({
                'error': f'Job configuration {job_config_id} not found'
            }), 404
    
    # Validate resume
    if resume_id:
        resume = Resume.query.filter_by(id=resume_id, user_id=user_id).first()
        if not resume:
            return jsonify({
                'error': f'Resume {resume_id} not found'
            }), 404
    
    # Check subscription status
    subscription = user.subscription
    if not subscription or not subscription.is_active():
        return jsonify({
            'error': 'You do not have an active subscription'
        }), 403
    
    # Check if user has reached their daily application limit
    today_applications = JobApplication.query.filter(
        JobApplication.user_id == user_id,
        JobApplication.application_date >= db.func.date('now')
    ).count()
    
    max_applications = subscription.plan.max_applications_per_day if subscription.plan else 0
    if today_applications >= max_applications:
        return jsonify({
            'error': f'You have reached your daily application limit ({max_applications})'
        }), 403
    
    # Start the job application task
    task = apply_to_jobs.delay(user_id, job_config_id, resume_id)
    
    return jsonify({
        'message': 'Job application task started',
        'task_id': task.id
    })


@api_bp.route('/job-tasks/search', methods=['POST'])
@jwt_required()
def start_job_search():
    """Start a job search task."""
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    
    data = request.json or {}
    job_config_id = data.get('job_config_id')
    
    # Validate job config
    if job_config_id:
        job_config = JobConfig.query.filter_by(id=job_config_id, user_id=user_id).first()
        if not job_config:
            return jsonify({
                'error': f'Job configuration {job_config_id} not found'
            }), 404
    
    # Check subscription status
    subscription = user.subscription
    if not subscription or not subscription.is_active():
        return jsonify({
            'error': 'You do not have an active subscription'
        }), 403
    
    # Start the job search task
    task = search_jobs.delay(user_id, job_config_id)
    
    return jsonify({
        'message': 'Job search task started',
        'task_id': task.id
    })


@api_bp.route('/job-tasks/generate-resume', methods=['POST'])
@jwt_required()
def start_resume_generation():
    """Start a resume generation task."""
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    
    data = request.json or {}
    base_resume_id = data.get('base_resume_id')
    job_title = data.get('job_title')
    company_name = data.get('company_name')
    
    # Validate required fields
    if not base_resume_id:
        return jsonify({
            'error': 'Base resume ID is required'
        }), 400
    
    if not job_title:
        return jsonify({
            'error': 'Job title is required'
        }), 400
    
    # Validate base resume
    base_resume = Resume.query.filter_by(id=base_resume_id, user_id=user_id).first()
    if not base_resume:
        return jsonify({
            'error': f'Resume {base_resume_id} not found'
        }), 404
    
    # Check subscription status
    subscription = user.subscription
    if not subscription or not subscription.is_active():
        return jsonify({
            'error': 'You do not have an active subscription'
        }), 403
    
    # Check if the subscription plan allows custom resume generation
    if not subscription.plan.has_custom_resume_generation:
        return jsonify({
            'error': 'Your subscription plan does not include custom resume generation'
        }), 403
    
    # Start the resume generation task
    task = generate_resume.delay(user_id, base_resume_id, job_title, company_name)
    
    return jsonify({
        'message': 'Resume generation task started',
        'task_id': task.id
    })


@api_bp.route('/job-tasks/<task_id>', methods=['GET'])
@jwt_required()
def get_task_status(task_id):
    """Get the status of a task."""
    user_id = get_jwt_identity()
    
    # Get the task result
    task_result = AsyncResult(task_id, app=celery)
    
    # Check if the task exists
    if not task_result.state:
        return jsonify({
            'error': f'Task {task_id} not found'
        }), 404
    
    # Get task info
    task_info = {
        'task_id': task_id,
        'status': task_result.state
    }
    
    # Add result if the task is completed
    if task_result.ready():
        if task_result.successful():
            result = task_result.result
            
            # Check if the task belongs to the user
            if isinstance(result, dict) and result.get('user_id') != user_id:
                return jsonify({
                    'error': 'You do not have permission to view this task'
                }), 403
            
            task_info['result'] = result
        else:
            task_info['error'] = str(task_result.result)
    
    return jsonify(task_info)


@api_bp.route('/job-tasks/<task_id>/cancel', methods=['POST'])
@jwt_required()
def cancel_task(task_id):
    """Cancel a task."""
    user_id = get_jwt_identity()
    
    # Get the task result
    task_result = AsyncResult(task_id, app=celery)
    
    # Check if the task exists
    if not task_result.state:
        return jsonify({
            'error': f'Task {task_id} not found'
        }), 404
    
    # Check if the task is already completed
    if task_result.ready():
        return jsonify({
            'error': 'Task is already completed'
        }), 400
    
    # Revoke the task
    task_result.revoke(terminate=True)
    
    return jsonify({
        'message': f'Task {task_id} has been canceled'
    })
