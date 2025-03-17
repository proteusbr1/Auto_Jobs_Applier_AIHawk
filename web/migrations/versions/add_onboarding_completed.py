"""
Add onboarding_completed column to users table.

Revision ID: add_onboarding_completed
Revises: add_subscription_model
Create Date: 2025-03-16 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_onboarding_completed'
down_revision = 'add_subscription_model'
branch_labels = None
depends_on = None


def upgrade():
    # Add onboarding_completed column to users table
    op.add_column('users', sa.Column('onboarding_completed', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    # Remove onboarding_completed column from users table
    op.drop_column('users', 'onboarding_completed')
