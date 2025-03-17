"""
ApplicationNote model for the AIHawk application.
"""
from datetime import datetime
from app import db


class ApplicationNote(db.Model):
    """
    ApplicationNote model for storing notes related to job applications.
    """
    __tablename__ = 'application_notes'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('job_applications.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    application = db.relationship('JobApplication', back_populates='notes')

    def __repr__(self):
        return f'<ApplicationNote {self.id} for application {self.application_id}>'

    def to_dict(self):
        """
        Convert the note to a dictionary.
        
        Returns:
            dict: Dictionary representation of the note
        """
        return {
            'id': self.id,
            'application_id': self.application_id,
            'content': self.content,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
