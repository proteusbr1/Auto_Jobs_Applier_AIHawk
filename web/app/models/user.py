"""
User model for the AIHawk application.
"""
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager


class User(UserMixin, db.Model):
    """
    User model for storing user account information.
    """
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    stripe_customer_id = db.Column(db.String(255), unique=True, nullable=True)
    onboarding_completed = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subscription = db.relationship('Subscription', uselist=False, back_populates='user', cascade='all, delete-orphan')
    job_configs = db.relationship('JobConfig', back_populates='user', cascade='all, delete-orphan')
    resumes = db.relationship('Resume', back_populates='user', cascade='all, delete-orphan')
    applications = db.relationship('JobApplication', back_populates='user', cascade='all, delete-orphan')
    notifications = db.relationship('Notification', back_populates='user', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<User {self.id} - {self.email}>'

    @property
    def password(self):
        """
        Prevent password from being accessed.
        """
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        """
        Set password to a hashed password.
        """
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        """
        Check if the provided password matches the hashed password.
        """
        return check_password_hash(self.password_hash, password)

    def get_full_name(self):
        """
        Return the user's full name.
        """
        return f'{self.first_name} {self.last_name}'

    def has_active_subscription(self):
        """
        Check if the user has an active subscription.
        """
        if self.subscription is not None:
            return self.subscription.is_active()
        return False
    
    def has_completed_onboarding(self):
        """
        Check if the user has completed the onboarding process.
        """
        return self.onboarding_completed
    
    def mark_onboarding_complete(self):
        """
        Mark the user's onboarding as complete.
        """
        self.onboarding_completed = True

    def get_subscription_plan(self):
        """
        Get the user's subscription plan.
        """
        if self.has_active_subscription():
            return self.subscription.plan
        return None

    def to_dict(self):
        """
        Convert the user to a dictionary.
        """
        return {
            'id': self.id,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'is_active': self.is_active,
            'is_admin': self.is_admin,
            'has_subscription': self.has_active_subscription(),
            'subscription_plan': self.get_subscription_plan(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


@login_manager.user_loader
def load_user(user_id):
    """
    Load a user given the user ID.
    """
    return User.query.get(int(user_id))
