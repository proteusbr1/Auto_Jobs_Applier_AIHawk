# Database Migrations

This directory contains database migrations for the Auto_Jobs_Applier_AIHawk web application.

## Creating a Migration

To create a new migration after making changes to the database models:

```bash
cd /path/to/Auto_Jobs_Applier_AIHawk
export FLASK_APP=wsgi
flask db migrate -m "Description of changes"
```

## Applying Migrations

To apply pending migrations:

```bash
cd /path/to/Auto_Jobs_Applier_AIHawk
export FLASK_APP=wsgi
flask db upgrade
```

## Reverting Migrations

To revert to a previous migration:

```bash
cd /path/to/Auto_Jobs_Applier_AIHawk
export FLASK_APP=wsgi
flask db downgrade
```

## Migration History

To view the migration history:

```bash
cd /path/to/Auto_Jobs_Applier_AIHawk
export FLASK_APP=wsgi
flask db history
```

## Initial Setup

The initial migration was created with:

```bash
cd /path/to/Auto_Jobs_Applier_AIHawk
export FLASK_APP=wsgi
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```
