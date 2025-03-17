"""
Resume models for the Auto_Jobs_Applier_AIHawk web application.
"""
from datetime import datetime
import os
from pathlib import Path

from flask import current_app
from app import db


class Resume(db.Model):
    """Resume model for storing user resume information."""
    
    __tablename__ = 'resumes'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    name = db.Column(db.String(100))
    description = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(255))
    file_type = db.Column(db.String(10))  # pdf, docx, html
    is_default = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    plain_text_content = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', back_populates='resumes')
    job_applications = db.relationship('JobApplication', back_populates='resume', lazy='dynamic')
    
    def __init__(self, user_id, name, file_path, file_type, description=None, is_default=False, plain_text_content=None):
        self.user_id = user_id
        self.name = name
        self.file_path = file_path
        self.file_type = file_type
        self.description = description
        self.is_default = is_default
        self.plain_text_content = plain_text_content
    
    def get_absolute_path(self):
        """Get the absolute path to the resume file."""
        user_data_dir = current_app.config['USER_DATA_DIR']
        return Path(user_data_dir, str(self.user_id), 'resumes', self.file_path)
    
    def delete_file(self):
        """Delete the resume file from the filesystem."""
        file_path = self.get_absolute_path()
        if os.path.exists(file_path):
            os.remove(file_path)
    
    def to_dict(self):
        """Convert the resume to a dictionary for API responses."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'file_type': self.file_type,
            'is_default': self.is_default,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f"<Resume {self.id} - {self.name}>"


class GeneratedResume(db.Model):
    """Generated resume model for storing AI-generated resumes."""
    
    __tablename__ = 'generated_resumes'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    base_resume_id = db.Column(db.Integer, db.ForeignKey('resumes.id'))
    job_title = db.Column(db.String(100))
    company_name = db.Column(db.String(100), nullable=True)
    file_path = db.Column(db.String(255))
    file_type = db.Column(db.String(10))  # pdf, docx, html
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User')
    base_resume = db.relationship('Resume')
    
    def __init__(self, user_id, base_resume_id, job_title, file_path, file_type, company_name=None):
        self.user_id = user_id
        self.base_resume_id = base_resume_id
        self.job_title = job_title
        self.company_name = company_name
        self.file_path = file_path
        self.file_type = file_type
    
    def get_absolute_path(self):
        """Get the absolute path to the generated resume file."""
        user_data_dir = current_app.config['USER_DATA_DIR']
        return Path(user_data_dir, str(self.user_id), 'generated_resumes', self.file_path)
    
    def delete_file(self):
        """Delete the generated resume file from the filesystem."""
        file_path = self.get_absolute_path()
        if os.path.exists(file_path):
            os.remove(file_path)
    
    def to_dict(self):
        """Convert the generated resume to a dictionary for API responses."""
        return {
            'id': self.id,
            'job_title': self.job_title,
            'company_name': self.company_name,
            'file_type': self.file_type,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f"<GeneratedResume {self.id} - {self.job_title}>"
