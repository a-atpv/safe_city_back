"""Switch from phone to email as primary identifier

Revision ID: 001_email_auth
Revises: 
Create Date: 2025-02-01

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001_email_auth'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add email column if it doesn't exist
    # SQLite doesn't support ALTER COLUMN, so we handle this carefully
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('users')]
    
    # Drop the old unique constraint on phone if it exists
    # Add email as required with unique constraint
    
    if 'email' not in columns:
        op.add_column('users', sa.Column('email', sa.String(255), nullable=True))
    
    # For existing users without email, generate placeholder email from phone
    op.execute("""
        UPDATE users 
        SET email = COALESCE(email, CONCAT(REPLACE(phone, '+', ''), '@placeholder.local'))
        WHERE email IS NULL
    """)
    
    # Now make email non-nullable and unique
    op.alter_column('users', 'email',
                    existing_type=sa.String(255),
                    nullable=False)
    
    # Create unique index on email
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    
    # Make phone nullable (remove NOT NULL constraint)
    op.alter_column('users', 'phone',
                    existing_type=sa.String(20),
                    nullable=True)
    
    # Drop unique constraint on phone (keep the index but not unique)
    op.drop_constraint('users_phone_key', 'users', type_='unique')


def downgrade():
    # Reverse the migration
    op.create_unique_constraint('users_phone_key', 'users', ['phone'])
    
    op.alter_column('users', 'phone',
                    existing_type=sa.String(20),
                    nullable=False)
    
    op.drop_index('ix_users_email', table_name='users')
    
    op.alter_column('users', 'email',
                    existing_type=sa.String(255),
                    nullable=True)
