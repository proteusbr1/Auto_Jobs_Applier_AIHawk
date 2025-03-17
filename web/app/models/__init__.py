"""
Models package for the Auto_Jobs_Applier_AIHawk web application.
"""
from app.models.user import User
from app.models.subscription import Subscription, SubscriptionPlan
from app.models.job_config import JobConfig
from app.models.resume import Resume, GeneratedResume
from app.models.job_application import JobApplication
from app.models.application_status_history import JobApplicationStatusUpdate
from app.models.application_note import ApplicationNote
from app.models.notification import Notification

__all__ = [
    'User',
    'Subscription',
    'SubscriptionPlan',
    'JobConfig',
    'Resume',
    'GeneratedResume',
    'JobApplication',
    'JobApplicationStatusUpdate',
    'ApplicationNote',
    'Notification'
]
