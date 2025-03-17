"""
Database initialization script for the Auto_Jobs_Applier_AIHawk web application.
"""
import os
import click
from flask.cli import with_appcontext
from app import create_app, db
from app.models import (
    User, Subscription, SubscriptionPlan, JobConfig, Resume, GeneratedResume,
    JobApplication, JobApplicationStatusUpdate
)


@click.command('init-db')
@with_appcontext
def init_db_command():
    """Initialize the database."""
    # Create all tables
    db.create_all()
    click.echo('Database tables created.')
    
    # Check if admin user exists
    admin = User.query.filter_by(username='admin').first()
    if admin is None:
        # Create admin user
        admin = User(
            username='admin',
            email='admin@example.com',
            password='admin',
            first_name='Admin',
            last_name='User',
            is_admin=True
        )
        db.session.add(admin)
        click.echo('Admin user created.')
    
    # Check if subscription plans exist
    if SubscriptionPlan.query.count() == 0:
        # Create subscription plans
        plans = [
            SubscriptionPlan(
                name='Free Trial',
                description='Free trial subscription with limited features',
                price_monthly=0.0,
                price_yearly=0.0,
                max_applications_per_day=5,
                max_concurrent_sessions=1,
                max_resumes=2,
                max_job_configs=1,
                has_priority_support=False,
                has_advanced_analytics=False,
                has_custom_resume_generation=False
            ),
            SubscriptionPlan(
                name='Basic',
                description='Basic subscription with essential features',
                price_monthly=9.99,
                price_yearly=99.99,
                max_applications_per_day=20,
                max_concurrent_sessions=1,
                max_resumes=5,
                max_job_configs=3,
                has_priority_support=False,
                has_advanced_analytics=False,
                has_custom_resume_generation=False
            ),
            SubscriptionPlan(
                name='Premium',
                description='Premium subscription with advanced features',
                price_monthly=19.99,
                price_yearly=199.99,
                max_applications_per_day=50,
                max_concurrent_sessions=2,
                max_resumes=10,
                max_job_configs=5,
                has_priority_support=True,
                has_advanced_analytics=True,
                has_custom_resume_generation=True
            ),
            SubscriptionPlan(
                name='Enterprise',
                description='Enterprise subscription with unlimited features',
                price_monthly=49.99,
                price_yearly=499.99,
                max_applications_per_day=100,
                max_concurrent_sessions=5,
                max_resumes=20,
                max_job_configs=10,
                has_priority_support=True,
                has_advanced_analytics=True,
                has_custom_resume_generation=True
            )
        ]
        
        for plan in plans:
            db.session.add(plan)
        
        click.echo('Subscription plans created.')
    
    # Commit changes
    db.session.commit()
    click.echo('Database initialized successfully.')


if __name__ == '__main__':
    app = create_app(os.environ.get('APP_ENV', 'default'))
    with app.app_context():
        init_db_command()
