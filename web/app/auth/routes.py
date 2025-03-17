"""
Authentication routes for the Auto_Jobs_Applier_AIHawk web application.
"""
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.urls import url_parse

from app import db
from app.auth import auth_bp
from app.auth.forms import LoginForm, RegistrationForm, ResetPasswordRequestForm, ResetPasswordForm
from app.models import User, Subscription, SubscriptionPlan


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid email or password', 'danger')
            return redirect(url_for('auth.login'))
        
        if not user.is_active:
            flash('This account has been deactivated. Please contact support.', 'danger')
            return redirect(url_for('auth.login'))
        
        login_user(user, remember=form.remember_me.data)
        user.update_last_login()
        
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('main.dashboard')
        
        flash('You have been logged in successfully!', 'success')
        return redirect(next_page)
    
    return render_template('auth/login.html', title='Sign In', form=form)


@auth_bp.route('/logout')
def logout():
    """Handle user logout."""
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Handle user registration."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data.lower(),
            password=form.password.data,
            first_name=form.first_name.data,
            last_name=form.last_name.data
        )
        db.session.add(user)
        
        # Create a free trial subscription
        free_plan = SubscriptionPlan.query.filter_by(name='Free Trial').first()
        if not free_plan:
            # Create a default free trial plan if it doesn't exist
            free_plan = SubscriptionPlan(
                name='Free Trial',
                description='Free trial subscription with limited features',
                price_monthly=0.0,
                price_yearly=0.0,
                max_applications_per_day=5,
                max_concurrent_sessions=1,
                max_resumes=2,
                max_job_configs=1,
                has_priority_support=False,
                has_advanced_analytics=False,
                has_custom_resume_generation=False
            )
            db.session.add(free_plan)
            db.session.flush()
        
        subscription = Subscription(
            user_id=user.id,
            plan_id=free_plan.id,
            status='active',
            is_trial=True,
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + current_app.config.get('TRIAL_DURATION', 30)
        )
        db.session.add(subscription)
        
        db.session.commit()
        
        flash('Congratulations, you are now a registered user! Please log in.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html', title='Register', form=form)


@auth_bp.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    """Handle password reset request."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user:
            # Send password reset email (to be implemented)
            pass
        
        flash('Check your email for instructions to reset your password.', 'info')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password_request.html', title='Reset Password', form=form)


@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Handle password reset with token."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    # Verify token and get user (to be implemented)
    user = None
    
    if not user:
        flash('Invalid or expired token', 'danger')
        return redirect(url_for('auth.reset_password_request'))
    
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been reset.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', title='Reset Password', form=form)


@auth_bp.route('/profile', methods=['GET'])
@login_required
def profile():
    """Display user profile."""
    return render_template('auth/profile.html', title='Profile')


@auth_bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    """Update user profile."""
    data = request.json
    
    if 'first_name' in data:
        current_user.first_name = data['first_name']
    
    if 'last_name' in data:
        current_user.last_name = data['last_name']
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Profile updated successfully'})


@auth_bp.route('/profile/change_password', methods=['POST'])
@login_required
def change_password():
    """Change user password."""
    data = request.json
    
    if not current_user.check_password(data.get('current_password')):
        return jsonify({'success': False, 'message': 'Current password is incorrect'}), 400
    
    current_user.set_password(data.get('new_password'))
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Password changed successfully'})
