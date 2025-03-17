"""
Subscription model for the AIHawk application.
"""
from datetime import datetime
from app import db


class SubscriptionPlan(db.Model):
    """
    SubscriptionPlan model for storing available subscription plans.
    """
    __tablename__ = 'subscription_plans'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    stripe_price_id = db.Column(db.String(255), unique=True, nullable=True)
    price = db.Column(db.Float, nullable=False)
    interval = db.Column(db.String(50), nullable=False, default='month')  # month, year
    features = db.Column(db.Text, nullable=True)  # JSON string of features
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<SubscriptionPlan {self.id} - {self.name} - ${self.price}/{self.interval}>'

    def to_dict(self):
        """
        Convert the subscription plan to a dictionary.
        
        Returns:
            dict: Dictionary representation of the subscription plan.
        """
        return {
            'id': self.id,
            'name': self.name,
            'stripe_price_id': self.stripe_price_id,
            'price': self.price,
            'interval': self.interval,
            'features': self.features,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Subscription(db.Model):
    """
    Subscription model for storing user subscription information.
    """
    __tablename__ = 'subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    stripe_subscription_id = db.Column(db.String(255), unique=True, nullable=True)
    plan = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), nullable=False, default='active')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', back_populates='subscription')

    def __repr__(self):
        return f'<Subscription {self.id} - {self.plan} - {self.status}>'

    def is_active(self):
        """
        Check if the subscription is active.
        
        Returns:
            bool: True if the subscription is active, False otherwise.
        """
        return self.status == 'active'

    def is_canceled(self):
        """
        Check if the subscription is canceled.
        
        Returns:
            bool: True if the subscription is canceled, False otherwise.
        """
        return self.status == 'canceled'

    def is_past_due(self):
        """
        Check if the subscription is past due.
        
        Returns:
            bool: True if the subscription is past due, False otherwise.
        """
        return self.status == 'past_due'

    def is_expired(self):
        """
        Check if the subscription is expired.
        
        Returns:
            bool: True if the subscription is expired, False otherwise.
        """
        return self.status == 'expired'

    def cancel(self):
        """
        Cancel the subscription.
        """
        self.status = 'canceled'
        db.session.commit()

    def reactivate(self):
        """
        Reactivate a canceled subscription.
        """
        if self.status == 'canceled':
            self.status = 'active'
            db.session.commit()

    def expire(self):
        """
        Mark the subscription as expired.
        """
        self.status = 'expired'
        db.session.commit()

    def to_dict(self):
        """
        Convert the subscription to a dictionary.
        
        Returns:
            dict: Dictionary representation of the subscription.
        """
        return {
            'id': self.id,
            'user_id': self.user_id,
            'stripe_subscription_id': self.stripe_subscription_id,
            'plan': self.plan,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
