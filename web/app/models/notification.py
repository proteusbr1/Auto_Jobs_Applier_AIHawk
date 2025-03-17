"""
Notification model for the AIHawk application.
"""
from datetime import datetime
from app import db


class Notification(db.Model):
    """
    Notification model for storing user notifications.
    """
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Notification details
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False, default='info')  # info, success, warning, error
    link = db.Column(db.String(1024), nullable=True)
    
    # Status
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    
    # System fields
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', back_populates='notifications')

    def __repr__(self):
        return f'<Notification {self.id} - {self.title} - {self.category}>'

    def mark_as_read(self):
        """
        Mark the notification as read.
        """
        self.is_read = True
        db.session.commit()

    def mark_as_unread(self):
        """
        Mark the notification as unread.
        """
        self.is_read = False
        db.session.commit()

    @classmethod
    def create_notification(cls, user_id, title, message, category='info', link=None):
        """
        Create a new notification.
        
        Args:
            user_id: ID of the user to notify
            title: Notification title
            message: Notification message
            category: Notification category (info, success, warning, error)
            link: Optional link to include in the notification
            
        Returns:
            The created notification
        """
        notification = cls(
            user_id=user_id,
            title=title,
            message=message,
            category=category,
            link=link
        )
        db.session.add(notification)
        db.session.commit()
        
        return notification

    def to_dict(self):
        """
        Convert the notification to a dictionary.
        
        Returns:
            dict: Dictionary representation of the notification
        """
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'message': self.message,
            'category': self.category,
            'link': self.link,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
