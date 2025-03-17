"""
Database initialization script for the AIHawk web application.
"""
import os
import sys
import time
import psycopg2
from flask_migrate import upgrade
from app import create_app, db

def wait_for_db(host, port, user, password, dbname, max_retries=10, retry_interval=3):
    """
    Wait for the database to be ready.
    
    Args:
        host (str): Database host
        port (int): Database port
        user (str): Database user
        password (str): Database password
        dbname (str): Database name
        max_retries (int): Maximum number of retries
        retry_interval (int): Interval between retries in seconds
        
    Returns:
        bool: True if database is ready, False otherwise
    """
    print(f"Waiting for database {host}:{port} to be ready...")
    
    for i in range(max_retries):
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=dbname
            )
            conn.close()
            print("Database is ready!")
            return True
        except psycopg2.OperationalError as e:
            print(f"Database not ready yet (attempt {i+1}/{max_retries}): {e}")
            time.sleep(retry_interval)
    
    return False

def init_db():
    """
    Initialize the database and run migrations.
    """
    # Get database configuration from environment variables
    postgres_user = os.environ.get('POSTGRES_USER', 'postgres')
    postgres_password = os.environ.get('POSTGRES_PASSWORD', 'postgres')
    postgres_db = os.environ.get('POSTGRES_DB', 'aihawk')
    
    # Wait for the database to be ready
    db_ready = wait_for_db(
        host='db',
        port=5432,
        user=postgres_user,
        password=postgres_password,
        dbname=postgres_db,
        max_retries=20,
        retry_interval=3
    )
    
    if not db_ready:
        print("Database is not ready after maximum retries. Exiting.")
        sys.exit(1)
    
    # Set the DATABASE_URL environment variable
    os.environ['DATABASE_URL'] = f'postgresql://{postgres_user}:{postgres_password}@db:5432/{postgres_db}'
    
    app = create_app('development')
    
    # No need to disable SQLAlchemy event system
    # This was causing errors
    
    with app.app_context():
        try:
            # Create tables directly with SQL
            db.engine.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                stripe_customer_id VARCHAR(255) UNIQUE,
                onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            print("Database tables created.")
            
            # Create admin user if environment variables are set
            admin_email = os.environ.get('ADMIN_EMAIL')
            admin_password = os.environ.get('ADMIN_PASSWORD')
            
            if admin_email and admin_password:
                try:
                    # Check if user already exists
                    admin_user = db.engine.execute(
                        f"SELECT * FROM users WHERE email = '{admin_email}'"
                    ).fetchone()
                    
                    if admin_user:
                        # Update user to be admin if not already
                        if not admin_user.is_admin:
                            db.engine.execute(
                                f"UPDATE users SET is_admin = TRUE WHERE email = '{admin_email}'"
                            )
                            print(f"User {admin_email} has been granted admin privileges.")
                        else:
                            print(f"User {admin_email} is already an admin.")
                    else:
                        # Create admin user
                        from werkzeug.security import generate_password_hash
                        
                        # Get first and last name from environment variables or use defaults
                        admin_first_name = os.environ.get('ADMIN_FIRST_NAME', 'Admin')
                        admin_last_name = os.environ.get('ADMIN_LAST_NAME', 'User')
                        
                        # Insert admin user
                        db.engine.execute(
                            f"""
                            INSERT INTO users (
                                email, password_hash, first_name, last_name, 
                                is_active, is_admin, onboarding_completed, 
                                created_at, updated_at
                            ) VALUES (
                                '{admin_email}', 
                                '{generate_password_hash(admin_password)}', 
                                '{admin_first_name}', 
                                '{admin_last_name}', 
                                TRUE, TRUE, TRUE, 
                                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                            )
                            """
                        )
                        print(f"Admin user {admin_email} created successfully.")
                except Exception as e:
                    print(f"Error creating admin user: {e}")
            
            print("Database initialized successfully.")
        except Exception as e:
            print(f"Error initializing database: {e}")
            # Continue anyway to allow the application to start

def init_db_command():
    """
    Initialize the database from the command line.
    """
    try:
        init_db()
    except Exception as e:
        print(f"Error in init_db_command: {e}")
        # Continue anyway to allow the application to start

if __name__ == '__main__':
    init_db_command()
