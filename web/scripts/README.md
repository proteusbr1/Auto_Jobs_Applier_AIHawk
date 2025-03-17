# AIHawk Scripts

This directory contains utility scripts for the AIHawk application.

## Create Admin User

The `create_admin.py` script allows you to create an admin user for the AIHawk application.

### Usage

```bash
# Make sure you're in the web directory
cd web

# Run the script with the required arguments
python scripts/create_admin.py --email admin@example.com --password securepassword --first-name Admin --last-name User

# For Docker environments, you can run the script inside the web container
docker-compose exec web python scripts/create_admin.py --email admin@example.com --password securepassword --first-name Admin --last-name User
```

### Arguments

- `--email`: Email address for the admin user (required)
- `--password`: Password for the admin user (required)
- `--first-name`: First name for the admin user (required)
- `--last-name`: Last name for the admin user (required)
- `--env`: Environment to run in (development, testing, production) (default: development)

### Behavior

- If a user with the specified email already exists and is not an admin, they will be granted admin privileges.
- If a user with the specified email already exists and is already an admin, no changes will be made.
- If no user with the specified email exists, a new admin user will be created.

## Backup Script

The `backup.sh` script is used to backup the database and user data.
