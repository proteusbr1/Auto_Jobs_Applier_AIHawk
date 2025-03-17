"""
Routes for the notifications blueprint.
"""
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from app import db
from app.notifications import notifications_bp
from app.models.notification import Notification


@notifications_bp.route('/')
@login_required
def index():
    """
    Display all notifications for the current user.
    """
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.is_read.asc(),
        Notification.created_at.desc()
    ).paginate(page=page, per_page=per_page)
    
    return render_template('notifications/index.html', notifications=notifications)


@notifications_bp.route('/unread')
@login_required
def unread():
    """
    Display unread notifications for the current user.
    """
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).order_by(Notification.created_at.desc()).paginate(page=page, per_page=per_page)
    
    return render_template('notifications/index.html', notifications=notifications, unread_only=True)


@notifications_bp.route('/mark-read/<int:notification_id>', methods=['POST'])
@login_required
def mark_read(notification_id):
    """
    Mark a notification as read.
    """
    notification = Notification.query.get_or_404(notification_id)
    
    # Check if the notification belongs to the current user
    if notification.user_id != current_user.id:
        flash('You do not have permission to access this notification.', 'error')
        return redirect(url_for('notifications.index'))
    
    notification.mark_as_read()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    
    flash('Notification marked as read.', 'success')
    return redirect(url_for('notifications.index'))


@notifications_bp.route('/mark-unread/<int:notification_id>', methods=['POST'])
@login_required
def mark_unread(notification_id):
    """
    Mark a notification as unread.
    """
    notification = Notification.query.get_or_404(notification_id)
    
    # Check if the notification belongs to the current user
    if notification.user_id != current_user.id:
        flash('You do not have permission to access this notification.', 'error')
        return redirect(url_for('notifications.index'))
    
    notification.mark_as_unread()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    
    flash('Notification marked as unread.', 'success')
    return redirect(url_for('notifications.index'))


@notifications_bp.route('/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    """
    Mark all notifications as read.
    """
    # Update all unread notifications for the current user
    Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).update({'is_read': True})
    
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    
    flash('All notifications marked as read.', 'success')
    return redirect(url_for('notifications.index'))


@notifications_bp.route('/delete/<int:notification_id>', methods=['POST'])
@login_required
def delete(notification_id):
    """
    Delete a notification.
    """
    notification = Notification.query.get_or_404(notification_id)
    
    # Check if the notification belongs to the current user
    if notification.user_id != current_user.id:
        flash('You do not have permission to access this notification.', 'error')
        return redirect(url_for('notifications.index'))
    
    db.session.delete(notification)
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    
    flash('Notification deleted.', 'success')
    return redirect(url_for('notifications.index'))


@notifications_bp.route('/delete-all', methods=['POST'])
@login_required
def delete_all():
    """
    Delete all notifications for the current user.
    """
    # Delete all notifications for the current user
    Notification.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    
    flash('All notifications deleted.', 'success')
    return redirect(url_for('notifications.index'))


@notifications_bp.route('/api/count')
@login_required
def api_count():
    """
    Get the count of unread notifications for the current user.
    """
    count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    return jsonify({'count': count})


@notifications_bp.route('/api/recent')
@login_required
def api_recent():
    """
    Get the most recent unread notifications for the current user.
    """
    limit = request.args.get('limit', 5, type=int)
    
    notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).order_by(Notification.created_at.desc()).limit(limit).all()
    
    return jsonify({
        'notifications': [notification.to_dict() for notification in notifications],
        'count': len(notifications)
    })
