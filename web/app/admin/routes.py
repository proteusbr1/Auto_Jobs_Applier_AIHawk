"""
Routes for the admin blueprint.
"""
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import datetime, timedelta

from app import db
from app.admin import admin_bp
from app.models.user import User
from app.models.subscription import Subscription
from app.models.job_application import JobApplication
from app.decorators import admin_required


@admin_bp.route('/')
@login_required
@admin_required
def index():
    """
    Admin dashboard home page.
    """
    # Get user statistics
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    
    # Get subscription statistics
    total_subscriptions = Subscription.query.count()
    active_subscriptions = Subscription.query.filter_by(status='active').count()
    
    # Get subscription breakdown by plan
    subscription_by_plan = db.session.query(
        Subscription.plan, func.count(Subscription.id)
    ).filter_by(status='active').group_by(Subscription.plan).all()
    
    # Format subscription by plan data for chart
    plan_labels = [plan for plan, _ in subscription_by_plan]
    plan_data = [count for _, count in subscription_by_plan]
    
    # Get application statistics
    total_applications = JobApplication.query.count()
    
    # Get application status breakdown
    application_by_status = db.session.query(
        JobApplication.status, func.count(JobApplication.id)
    ).group_by(JobApplication.status).all()
    
    # Format application status data for chart
    status_labels = [status for status, _ in application_by_status]
    status_data = [count for _, count in application_by_status]
    
    # Get recent users
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    
    # Get recent subscriptions
    recent_subscriptions = Subscription.query.order_by(Subscription.created_at.desc()).limit(5).all()
    
    return render_template(
        'admin/index.html',
        total_users=total_users,
        active_users=active_users,
        total_subscriptions=total_subscriptions,
        active_subscriptions=active_subscriptions,
        subscription_by_plan=subscription_by_plan,
        plan_labels=plan_labels,
        plan_data=plan_data,
        total_applications=total_applications,
        application_by_status=application_by_status,
        status_labels=status_labels,
        status_data=status_data,
        recent_users=recent_users,
        recent_subscriptions=recent_subscriptions
    )


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    """
    User management page.
    """
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    users = User.query.order_by(User.created_at.desc()).paginate(page=page, per_page=per_page)
    
    return render_template('admin/users.html', users=users)


@admin_bp.route('/users/<int:user_id>')
@login_required
@admin_required
def user_detail(user_id):
    """
    User detail page.
    """
    user = User.query.get_or_404(user_id)
    
    # Get user's subscription
    subscription = user.subscription
    
    # Get user's job applications
    applications = JobApplication.query.filter_by(user_id=user_id).order_by(JobApplication.created_at.desc()).limit(10).all()
    
    # Get application statistics
    application_count = JobApplication.query.filter_by(user_id=user_id).count()
    
    # Get application status breakdown
    application_by_status = db.session.query(
        JobApplication.status, func.count(JobApplication.id)
    ).filter_by(user_id=user_id).group_by(JobApplication.status).all()
    
    return render_template(
        'admin/user_detail.html',
        user=user,
        subscription=subscription,
        applications=applications,
        application_count=application_count,
        application_by_status=application_by_status
    )


@admin_bp.route('/users/<int:user_id>/toggle_active', methods=['POST'])
@login_required
@admin_required
def toggle_user_active(user_id):
    """
    Toggle user active status.
    """
    user = User.query.get_or_404(user_id)
    
    # Don't allow deactivating your own account
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'error')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    
    user.is_active = not user.is_active
    db.session.commit()
    
    status = 'activated' if user.is_active else 'deactivated'
    flash(f'User {user.email} has been {status}.', 'success')
    
    return redirect(url_for('admin.user_detail', user_id=user_id))


@admin_bp.route('/users/<int:user_id>/toggle_admin', methods=['POST'])
@login_required
@admin_required
def toggle_user_admin(user_id):
    """
    Toggle user admin status.
    """
    user = User.query.get_or_404(user_id)
    
    # Don't allow removing admin from your own account
    if user.id == current_user.id:
        flash('You cannot remove admin privileges from your own account.', 'error')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    
    user.is_admin = not user.is_admin
    db.session.commit()
    
    status = 'granted' if user.is_admin else 'removed'
    flash(f'Admin privileges have been {status} for user {user.email}.', 'success')
    
    return redirect(url_for('admin.user_detail', user_id=user_id))


@admin_bp.route('/subscriptions')
@login_required
@admin_required
def subscriptions():
    """
    Subscription management page.
    """
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    subscriptions = Subscription.query.order_by(Subscription.created_at.desc()).paginate(page=page, per_page=per_page)
    
    return render_template('admin/subscriptions.html', subscriptions=subscriptions)


@admin_bp.route('/analytics')
@login_required
@admin_required
def analytics():
    """
    Analytics dashboard.
    """
    # Get date range for analytics
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    
    # Get user growth data
    user_growth = db.session.query(
        func.date(User.created_at).label('date'),
        func.count(User.id).label('count')
    ).filter(User.created_at >= start_date).group_by(func.date(User.created_at)).all()
    
    # Format user growth data for chart
    user_growth_dates = [date.strftime('%Y-%m-%d') for date, _ in user_growth]
    user_growth_counts = [count for _, count in user_growth]
    
    # Get subscription growth data
    subscription_growth = db.session.query(
        func.date(Subscription.created_at).label('date'),
        func.count(Subscription.id).label('count')
    ).filter(Subscription.created_at >= start_date).group_by(func.date(Subscription.created_at)).all()
    
    # Format subscription growth data for chart
    subscription_growth_dates = [date.strftime('%Y-%m-%d') for date, _ in subscription_growth]
    subscription_growth_counts = [count for _, count in subscription_growth]
    
    # Get application growth data
    application_growth = db.session.query(
        func.date(JobApplication.created_at).label('date'),
        func.count(JobApplication.id).label('count')
    ).filter(JobApplication.created_at >= start_date).group_by(func.date(JobApplication.created_at)).all()
    
    # Format application growth data for chart
    application_growth_dates = [date.strftime('%Y-%m-%d') for date, _ in application_growth]
    application_growth_counts = [count for _, count in application_growth]
    
    return render_template(
        'admin/analytics.html',
        user_growth_dates=user_growth_dates,
        user_growth_counts=user_growth_counts,
        subscription_growth_dates=subscription_growth_dates,
        subscription_growth_counts=subscription_growth_counts,
        application_growth_dates=application_growth_dates,
        application_growth_counts=application_growth_counts
    )


@admin_bp.route('/system')
@login_required
@admin_required
def system():
    """
    System health monitoring.
    """
    # Get application success rate
    total_applications = JobApplication.query.count()
    successful_applications = JobApplication.query.filter(
        JobApplication.status.in_(['applied', 'interview', 'offer'])
    ).count()
    
    if total_applications > 0:
        success_rate = (successful_applications / total_applications) * 100
    else:
        success_rate = 0
    
    # Get error rates
    # This would typically come from your logging system
    error_rates = {
        'application_errors': 5.2,
        'payment_errors': 1.3,
        'api_errors': 2.7
    }
    
    return render_template(
        'admin/system.html',
        total_applications=total_applications,
        successful_applications=successful_applications,
        success_rate=success_rate,
        error_rates=error_rates
    )
