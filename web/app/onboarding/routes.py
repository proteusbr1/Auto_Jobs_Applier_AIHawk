"""
Routes for the onboarding blueprint.
"""
from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_required, current_user

from app import db
from app.onboarding import onboarding_bp
from app.models.user import User
from app.stripe_config import SUBSCRIPTION_PLANS


@onboarding_bp.route('/')
@login_required
def index():
    """
    Onboarding home page.
    """
    # Check if user has completed onboarding
    if current_user.has_completed_onboarding():
        return redirect(url_for('main.dashboard'))
    
    # Get the current onboarding step
    current_step = session.get('onboarding_step', 1)
    
    # Render the appropriate template based on the current step
    if current_step == 1:
        return redirect(url_for('onboarding.welcome'))
    elif current_step == 2:
        return redirect(url_for('onboarding.subscription'))
    elif current_step == 3:
        return redirect(url_for('onboarding.resume'))
    elif current_step == 4:
        return redirect(url_for('onboarding.job_preferences'))
    else:
        return redirect(url_for('onboarding.complete'))


@onboarding_bp.route('/welcome')
@login_required
def welcome():
    """
    Welcome page for new users.
    """
    # Set the current onboarding step
    session['onboarding_step'] = 1
    
    return render_template('onboarding/welcome.html')


@onboarding_bp.route('/subscription')
@login_required
def subscription():
    """
    Subscription selection page.
    """
    # Set the current onboarding step
    session['onboarding_step'] = 2
    
    # Check if user already has an active subscription
    has_subscription = current_user.subscription and current_user.subscription.is_active()
    
    return render_template(
        'onboarding/subscription.html',
        plans=SUBSCRIPTION_PLANS,
        has_subscription=has_subscription,
        subscription=current_user.subscription
    )


@onboarding_bp.route('/resume')
@login_required
def resume():
    """
    Resume upload page.
    """
    # Set the current onboarding step
    session['onboarding_step'] = 3
    
    # Check if user has a subscription
    if not current_user.has_active_subscription():
        flash('Please select a subscription plan before uploading your resume.', 'warning')
        return redirect(url_for('onboarding.subscription'))
    
    # Get user's resumes
    resumes = current_user.resumes
    
    return render_template('onboarding/resume.html', resumes=resumes)


@onboarding_bp.route('/job-preferences')
@login_required
def job_preferences():
    """
    Job preferences configuration page.
    """
    # Set the current onboarding step
    session['onboarding_step'] = 4
    
    # Check if user has a subscription and resume
    if not current_user.has_active_subscription():
        flash('Please select a subscription plan before setting job preferences.', 'warning')
        return redirect(url_for('onboarding.subscription'))
    
    if not current_user.resumes:
        flash('Please upload a resume before setting job preferences.', 'warning')
        return redirect(url_for('onboarding.resume'))
    
    # Get user's job configurations
    job_configs = current_user.job_configs
    
    return render_template('onboarding/job_preferences.html', job_configs=job_configs)


@onboarding_bp.route('/complete')
@login_required
def complete():
    """
    Onboarding completion page.
    """
    # Set the current onboarding step
    session['onboarding_step'] = 5
    
    # Check if user has completed all previous steps
    if not current_user.has_active_subscription():
        flash('Please select a subscription plan to complete onboarding.', 'warning')
        return redirect(url_for('onboarding.subscription'))
    
    if not current_user.resumes:
        flash('Please upload a resume to complete onboarding.', 'warning')
        return redirect(url_for('onboarding.resume'))
    
    if not current_user.job_configs:
        flash('Please set job preferences to complete onboarding.', 'warning')
        return redirect(url_for('onboarding.job_preferences'))
    
    # Mark onboarding as complete
    current_user.mark_onboarding_complete()
    db.session.commit()
    
    # Clear onboarding session data
    session.pop('onboarding_step', None)
    
    return render_template('onboarding/complete.html')


@onboarding_bp.route('/skip')
@login_required
def skip():
    """
    Skip onboarding and go directly to the dashboard.
    """
    # Mark onboarding as complete
    current_user.mark_onboarding_complete()
    db.session.commit()
    
    # Clear onboarding session data
    session.pop('onboarding_step', None)
    
    flash('You can always complete your profile and subscription from the dashboard.', 'info')
    return redirect(url_for('main.dashboard'))
