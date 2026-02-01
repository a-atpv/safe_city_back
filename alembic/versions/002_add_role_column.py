"""Add role column to users

Revision ID: 002_add_role_column
Revises: 001_email_auth
Create Date: 2025-02-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_add_role_column'
down_revision = '001_email_auth'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('role', sa.String(), server_default='user', nullable=False))


def downgrade():
    op.drop_column('users', 'role')
