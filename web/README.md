# AIHawk Web Application

This is the web version of the AIHawk application, a multi-user subscription-based service for automated job applications on LinkedIn.

## Development Setup

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- PostgreSQL database
- Node.js and npm (for frontend assets)
- Docker and Docker Compose (optional, for containerized setup)

### Local Development Setup

#### 1. Clone the repository

```bash
git clone https://github.com/yourusername/Auto_Jobs_Applier_AIHawk.git
cd Auto_Jobs_Applier_AIHawk/web
```

#### 2. Create and activate a virtual environment

```bash
# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows
venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate
```

#### 3. Install dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies (if applicable)
npm install
```

#### 4. Set up environment variables

Create a `.env` file in the web directory with the following variables:

```
# Flask configuration
FLASK_APP=run.py
FLASK_ENV=development
SECRET_KEY=your-secret-key

# Database configuration
DATABASE_URL=postgresql://username:password@localhost/aihawk_db

# Stripe configuration (for payment processing)
STRIPE_PUBLISHABLE_KEY=your-stripe-publishable-key
STRIPE_SECRET_KEY=your-stripe-secret-key
STRIPE_WEBHOOK_SECRET=your-stripe-webhook-secret

# OpenAI configuration (for AI features)
OPENAI_API_KEY=your-openai-api-key
```

#### 5. Initialize the database

```bash
# Create the database (if it doesn't exist)
createdb aihawk_db

# Run database migrations
flask db upgrade

# Create an admin user (optional)
python scripts/create_admin.py --email admin@example.com --password securepassword --first-name Admin --last-name User
```

Alternatively, you can set the following environment variables in your `.env` file to create an admin user automatically when initializing the database:

```
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=securepassword
ADMIN_FIRST_NAME=Admin
ADMIN_LAST_NAME=User
```

#### 6. Run the development server

```bash
# Start the Flask development server
flask run

# Or with specific host and port
flask run --host=0.0.0.0 --port=5000
```

The application will be available at http://localhost:5000

### Docker Development Setup

If you prefer to use Docker for development:

#### 1. Build and start the containers

```bash
# Build and start the containers in development mode
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

#### 2. Run database migrations and create an admin user

```bash
# Run migrations inside the container
docker-compose exec web flask db upgrade

# Create an admin user (optional)
docker-compose exec web python scripts/create_admin.py --email admin@example.com --password securepassword --first-name Admin --last-name User
```

Alternatively, you can set the following environment variables in your `.env` file to create an admin user automatically when initializing the database:

```
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=securepassword
ADMIN_FIRST_NAME=Admin
ADMIN_LAST_NAME=User
```

The application will be available at http://localhost:5000

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest

# Run tests with coverage report
pytest --cov=app
```

### Code Linting

```bash
# Run flake8 for Python linting
flake8 app

# Run eslint for JavaScript linting (if applicable)
npm run lint
```

### Database Migrations

When you make changes to the database models:

```bash
# Generate a new migration
flask db migrate -m "Description of changes"

# Apply the migration
flask db upgrade
```

### Frontend Asset Compilation (if applicable)

```bash
# Compile assets for development
npm run dev

# Compile assets for production
npm run build
```

## Project Structure

```
web/
├── app/                    # Application package
│   ├── __init__.py         # Application factory
│   ├── admin/              # Admin blueprint
│   ├── auth/               # Authentication blueprint
│   ├── billing/            # Billing and subscription blueprint
│   ├── main/               # Main blueprint
│   ├── models/             # Database models
│   ├── notifications/      # Notifications blueprint
│   ├── onboarding/         # User onboarding blueprint
│   ├── static/             # Static files (CSS, JS, images)
│   └── templates/          # Jinja2 templates
├── migrations/             # Database migrations
├── tests/                  # Test package
├── .env                    # Environment variables (not in version control)
├── .flaskenv               # Flask environment variables
├── config.py               # Application configuration
├── requirements.txt        # Python dependencies
└── run.py                  # Application entry point
```

## Deployment

For production deployment, see the deployment instructions in `DEPLOYMENT.md`.
