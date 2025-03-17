#!/usr/bin/env python
"""
Script to create an admin user for the AIHawk application.
"""
import os
import sys
import argparse
from werkzeug.security import generate_password_hash
from datetime import datetime

# Add the parent directory to the path so we can import the app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models.user import User

def create_admin_user(email, password, first_name, last_name):
    """
    Create an admin user with the given credentials.
    
    Args:
        email (str): Email address for the admin user
        password (str): Password for the admin user
        first_name (str): First name for the admin user
        last_name (str): Last name for the admin user
        
    Returns:
        User: The created admin user
    """
    # Check if user already exists
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        print(f"User with email {email} already exists.")
        
        # If user exists but is not admin, make them admin
        if not existing_user.is_admin:
            existing_user.is_admin = True
            db.session.commit()
            print(f"User {email} has been granted admin privileges.")
        else:
            print(f"User {email} is already an admin.")
            
        return existing_user
    
    # Create new admin user
    admin_user = User(
        email=email,
        password_hash=generate_password_hash(password),
        first_name=first_name,
        last_name=last_name,
        is_active=True,
        is_admin=True,
        onboarding_completed=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.session.add(admin_user)
    db.session.commit()
    
    print(f"Admin user {email} created successfully.")
    return admin_user

def main():
    """
    Main function to create an admin user.
    """
    parser = argparse.ArgumentParser(description='Create an admin user for the AIHawk application.')
    parser.add_argument('--email', required=True, help='Email address for the admin user')
    parser.add_argument('--password', required=True, help='Password for the admin user')
    parser.add_argument('--first-name', required=True, help='First name for the admin user')
    parser.add_argument('--last-name', required=True, help='Last name for the admin user')
    parser.add_argument('--env', default='development', help='Environment to run in (development, testing, production)')
    
    args = parser.parse_args()
    
    # Create the Flask app with the specified environment
    app = create_app(args.env)
    
    # Create the admin user within the app context
    with app.app_context():
        create_admin_user(args.email, args.password, args.first_name, args.last_name)

if __name__ == '__main__':
    main()
