"""
JobApplication model for the AIHawk application.
"""
from datetime import datetime
from app import db


class JobApplication(db.Model):
    """
    JobApplication model for storing job application information.
    """
    __tablename__ = 'job_applications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    job_config_id = db.Column(db.Integer, db.ForeignKey('job_configs.id'), nullable=False)
    resume_id = db.Column(db.Integer, db.ForeignKey('resumes.id'), nullable=True)
    
    # Job details
    job_title = db.Column(db.String(255), nullable=False)
    company = db.Column(db.String(255), nullable=False)
    location = db.Column(db.String(255), nullable=True)
    job_description = db.Column(db.Text, nullable=True)
    job_url = db.Column(db.String(1024), nullable=True)
    
    # Application details
    status = db.Column(db.String(50), nullable=False, default='pending')  # pending, applied, rejected, interview, offer
    applied_at = db.Column(db.DateTime, nullable=True)
    last_status_change = db.Column(db.DateTime, nullable=True)
    
    # System fields
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', back_populates='applications')
    job_config = db.relationship('JobConfig', back_populates='applications')
    resume = db.relationship('Resume', back_populates='applications')
    notes = db.relationship('ApplicationNote', back_populates='application', cascade='all, delete-orphan')
    status_history = db.relationship('ApplicationStatusHistory', back_populates='application', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<JobApplication {self.id} - {self.job_title} at {self.company} - {self.status}>'

    def update_status(self, new_status, note=None):
        """
        Update the application status and create a status history entry.
        
        Args:
            new_status: New status value
            note: Optional note about the status change
        """
        if new_status != self.status:
            # Create status history entry
            from app.models.application_status_history import ApplicationStatusHistory, JobApplicationStatusUpdate
            
            history_entry = ApplicationStatusHistory(
                application_id=self.id,
                old_status=self.status,
                new_status=new_status,
                note=note
            )
            db.session.add(history_entry)
            
            # Update application status
            self.status = new_status
            self.last_status_change = datetime.utcnow()
            
            db.session.commit()
            return True
        return False

    def add_note(self, content):
        """
        Add a note to the application.
        
        Args:
            content: Note content
        
        Returns:
            The created note
        """
        from app.models.application_note import ApplicationNote
        
        note = ApplicationNote(
            application_id=self.id,
            content=content
        )
        db.session.add(note)
        db.session.commit()
        
        return note

    def to_dict(self):
        """
        Convert the application to a dictionary.
        
        Returns:
            dict: Dictionary representation of the application
        """
        return {
            'id': self.id,
            'user_id': self.user_id,
            'job_config_id': self.job_config_id,
            'resume_id': self.resume_id,
            'job_title': self.job_title,
            'company': self.company,
            'location': self.location,
            'status': self.status,
            'applied_at': self.applied_at.isoformat() if self.applied_at else None,
            'last_status_change': self.last_status_change.isoformat() if self.last_status_change else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
