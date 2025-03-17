"""
Job configuration models for the Auto_Jobs_Applier_AIHawk web application.
"""
from datetime import datetime
import json

from app import db


class JobConfig(db.Model):
    """Job search configuration model for storing user-specific job search settings."""
    
    __tablename__ = 'job_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    name = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    is_default = db.Column(db.Boolean, default=False)
    remote = db.Column(db.Boolean, default=False)
    distance = db.Column(db.Integer, default=10)
    apply_once_at_company = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # JSON fields (stored as strings)
    _experience_levels = db.Column('experience_levels', db.Text, default='{}')
    _job_types = db.Column('job_types', db.Text, default='{}')
    _date_filters = db.Column('date_filters', db.Text, default='{}')
    _searches = db.Column('searches', db.Text, default='[]')
    _company_blacklist = db.Column('company_blacklist', db.Text, default='[]')
    _title_blacklist = db.Column('title_blacklist', db.Text, default='[]')
    _job_applicants_threshold = db.Column('job_applicants_threshold', db.Text, default='{}')
    
    # Relationships
    user = db.relationship('User', back_populates='job_configs')
    job_applications = db.relationship('JobApplication', back_populates='job_config', lazy='dynamic')
    
    @property
    def experience_levels(self):
        """Get the experience levels as a dictionary."""
        return json.loads(self._experience_levels)
    
    @experience_levels.setter
    def experience_levels(self, value):
        """Set the experience levels from a dictionary."""
        self._experience_levels = json.dumps(value)
    
    @property
    def job_types(self):
        """Get the job types as a dictionary."""
        return json.loads(self._job_types)
    
    @job_types.setter
    def job_types(self, value):
        """Set the job types from a dictionary."""
        self._job_types = json.dumps(value)
    
    @property
    def date_filters(self):
        """Get the date filters as a dictionary."""
        return json.loads(self._date_filters)
    
    @date_filters.setter
    def date_filters(self, value):
        """Set the date filters from a dictionary."""
        self._date_filters = json.dumps(value)
    
    @property
    def searches(self):
        """Get the searches as a list."""
        return json.loads(self._searches)
    
    @searches.setter
    def searches(self, value):
        """Set the searches from a list."""
        self._searches = json.dumps(value)
    
    @property
    def company_blacklist(self):
        """Get the company blacklist as a list."""
        return json.loads(self._company_blacklist)
    
    @company_blacklist.setter
    def company_blacklist(self, value):
        """Set the company blacklist from a list."""
        self._company_blacklist = json.dumps(value)
    
    @property
    def title_blacklist(self):
        """Get the title blacklist as a list."""
        return json.loads(self._title_blacklist)
    
    @title_blacklist.setter
    def title_blacklist(self, value):
        """Set the title blacklist from a list."""
        self._title_blacklist = json.dumps(value)
    
    @property
    def job_applicants_threshold(self):
        """Get the job applicants threshold as a dictionary."""
        return json.loads(self._job_applicants_threshold)
    
    @job_applicants_threshold.setter
    def job_applicants_threshold(self, value):
        """Set the job applicants threshold from a dictionary."""
        self._job_applicants_threshold = json.dumps(value)
    
    def to_dict(self):
        """Convert the job config to a dictionary for API responses."""
        return {
            'id': self.id,
            'name': self.name,
            'is_active': self.is_active,
            'is_default': self.is_default,
            'remote': self.remote,
            'distance': self.distance,
            'apply_once_at_company': self.apply_once_at_company,
            'experience_levels': self.experience_levels,
            'job_types': self.job_types,
            'date_filters': self.date_filters,
            'searches': self.searches,
            'company_blacklist': self.company_blacklist,
            'title_blacklist': self.title_blacklist,
            'job_applicants_threshold': self.job_applicants_threshold,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f"<JobConfig {self.id} - {self.name}>"
