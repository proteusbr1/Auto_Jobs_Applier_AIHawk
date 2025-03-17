"""
Routes for the main blueprint of the Auto_Jobs_Applier_AIHawk web application.
"""
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import desc

from app import db
from app.main import main_bp
from app.models import User, JobConfig, Resume, JobApplication, SubscriptionPlan, Subscription


@main_bp.route('/')
def index():
    """Render the landing page."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    # Get subscription plans for pricing section
    try:
        plans = SubscriptionPlan.query.all()
    except Exception as e:
        current_app.logger.error(f"Database error: {str(e)}")
        plans = []  # Provide an empty list as fallback
    
    return render_template('main/index.html', plans=plans)


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Render the dashboard page."""
    # Get recent job applications
    recent_applications = JobApplication.query.filter_by(user_id=current_user.id) \
        .order_by(desc(JobApplication.application_date)) \
        .limit(5) \
        .all()
    
    # Get application statistics
    total_applications = JobApplication.query.filter_by(user_id=current_user.id).count()
    
    # Get status counts
    status_counts = db.session.query(
        JobApplication.status, db.func.count(JobApplication.id)
    ).filter(
        JobApplication.user_id == current_user.id
    ).group_by(
        JobApplication.status
    ).all()
    
    status_stats = {status: count for status, count in status_counts}
    
    # Get active job configs
    active_configs = JobConfig.query.filter_by(user_id=current_user.id, is_active=True).all()
    
    # Get subscription info
    subscription = current_user.subscription
    
    return render_template(
        'main/dashboard.html',
        recent_applications=recent_applications,
        total_applications=total_applications,
        status_stats=status_stats,
        active_configs=active_configs,
        subscription=subscription
    )


@main_bp.route('/job-configs')
@login_required
def job_configs():
    """Render the job configurations page."""
    configs = JobConfig.query.filter_by(user_id=current_user.id).all()
    return render_template('main/job_configs.html', configs=configs)


@main_bp.route('/job-configs/<int:config_id>')
@login_required
def job_config_detail(config_id):
    """Render the job configuration detail page."""
    config = JobConfig.query.filter_by(id=config_id, user_id=current_user.id).first_or_404()
    return render_template('main/job_config_detail.html', config=config)


@main_bp.route('/resumes')
@login_required
def resumes():
    """Render the resumes page."""
    resumes = Resume.query.filter_by(user_id=current_user.id).all()
    return render_template('main/resumes.html', resumes=resumes)


@main_bp.route('/resumes/<int:resume_id>')
@login_required
def resume_detail(resume_id):
    """Render the resume detail page."""
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    return render_template('main/resume_detail.html', resume=resume)


@main_bp.route('/applications')
@login_required
def applications():
    """Render the job applications page."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')
    company = request.args.get('company')
    search_term = request.args.get('search_term')
    
    # Build query
    query = JobApplication.query.filter_by(user_id=current_user.id)
    
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
    
    return render_template(
        'main/applications.html',
        applications=paginated_apps.items,
        pagination=paginated_apps,
        status=status,
        company=company,
        search_term=search_term
    )


@main_bp.route('/applications/<int:application_id>')
@login_required
def application_detail(application_id):
    """Render the job application detail page."""
    application = JobApplication.query.filter_by(id=application_id, user_id=current_user.id).first_or_404()
    return render_template('main/application_detail.html', application=application)


@main_bp.route('/profile')
@login_required
def profile():
    """Render the user profile page."""
    return render_template('main/profile.html')


@main_bp.route('/subscription')
@login_required
def subscription():
    """Render the subscription page."""
    try:
        plans = SubscriptionPlan.query.all()
    except Exception as e:
        current_app.logger.error(f"Database error: {str(e)}")
        plans = []  # Provide an empty list as fallback
    
    user_subscription = current_user.subscription
    return render_template('main/subscription.html', plans=plans, subscription=user_subscription)


@main_bp.route('/privacy')
def privacy():
    """Render the privacy policy page."""
    return render_template('main/privacy.html')


@main_bp.route('/terms')
def terms():
    """Render the terms of service page."""
    return render_template('main/terms.html')


@main_bp.route('/contact')
def contact():
    """Render the contact page."""
    return render_template('main/contact.html')
