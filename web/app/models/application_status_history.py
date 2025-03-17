"""
ApplicationStatusHistory model for the AIHawk application.
"""
from datetime import datetime
from app import db


class ApplicationStatusHistory(db.Model):
    """
    ApplicationStatusHistory model for tracking job application status changes.
    """
    __tablename__ = 'application_status_history'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('job_applications.id'), nullable=False)
    old_status = db.Column(db.String(50), nullable=True)
    new_status = db.Column(db.String(50), nullable=False)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    application = db.relationship('JobApplication', back_populates='status_history')

    def __repr__(self):
        return f'<ApplicationStatusHistory {self.id} - {self.old_status} -> {self.new_status}>'

    def to_dict(self):
        """
        Convert the status history entry to a dictionary.
        
        Returns:
            dict: Dictionary representation of the status history entry
        """
        return {
            'id': self.id,
            'application_id': self.application_id,
            'old_status': self.old_status,
            'new_status': self.new_status,
            'note': self.note,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# Alias for backward compatibility
JobApplicationStatusUpdate = ApplicationStatusHistory
