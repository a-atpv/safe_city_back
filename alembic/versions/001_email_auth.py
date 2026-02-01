"""Initial schema with email auth

Revision ID: 001_email_auth
Revises: 
Create Date: 2025-02-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_email_auth'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # --- Cleanup (Drop if exists to avoid conflicts) ---
    op.execute("DROP TYPE IF EXISTS userstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS subscriptionstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS callstatus CASCADE")

    # --- Enums (Safe Create) ---
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userstatus') THEN
            CREATE TYPE userstatus AS ENUM ('active', 'inactive', 'blocked');
        END IF;
    END$$;
    """)

    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'subscriptionstatus') THEN
            CREATE TYPE subscriptionstatus AS ENUM ('active', 'expired', 'cancelled', 'pending');
        END IF;
    END$$;
    """)

    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'callstatus') THEN
            CREATE TYPE callstatus AS ENUM ('created', 'searching', 'offer_sent', 'accepted', 'en_route', 'arrived', 'completed', 'cancelled_by_user', 'cancelled_by_system');
        END IF;
    END$$;
    """)

    # --- Users ---
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('avatar_url', sa.String(length=500), nullable=True),
        sa.Column('status', sa.Enum('active', 'inactive', 'blocked', name='userstatus'), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=True),
        sa.Column('last_latitude', sa.Float(), nullable=True),
        sa.Column('last_longitude', sa.Float(), nullable=True),
        sa.Column('last_location_update', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)

    # --- Subscriptions ---
    op.create_table('subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('active', 'expired', 'cancelled', 'pending', name='subscriptionstatus'), nullable=True),
        sa.Column('plan_type', sa.String(length=50), nullable=True),
        sa.Column('price', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('payment_provider', sa.String(length=50), nullable=True),
        sa.Column('external_subscription_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_subscriptions_id'), 'subscriptions', ['id'], unique=False)

    # --- User Devices ---
    op.create_table('user_devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('device_token', sa.String(length=500), nullable=True),
        sa.Column('device_type', sa.String(length=20), nullable=True),
        sa.Column('device_model', sa.String(length=100), nullable=True),
        sa.Column('app_version', sa.String(length=20), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_devices_id'), 'user_devices', ['id'], unique=False)

    # --- Security Companies ---
    op.create_table('security_companies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('legal_name', sa.String(length=255), nullable=True),
        sa.Column('logo_url', sa.String(length=500), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('address', sa.String(length=500), nullable=True),
        sa.Column('service_latitude', sa.Float(), nullable=True),
        sa.Column('service_longitude', sa.Float(), nullable=True),
        sa.Column('service_radius_km', sa.Float(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('is_accepting_calls', sa.Boolean(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('response_timeout_seconds', sa.Integer(), nullable=True),
        sa.Column('total_calls', sa.Integer(), nullable=True),
        sa.Column('completed_calls', sa.Integer(), nullable=True),
        sa.Column('average_response_time', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_security_companies_id'), 'security_companies', ['id'], unique=False)

    # --- Emergency Calls ---
    op.create_table('emergency_calls',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('created', 'searching', 'offer_sent', 'accepted', 'en_route', 'arrived', 'completed', 'cancelled_by_user', 'cancelled_by_system', name='callstatus'), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('address', sa.String(length=500), nullable=True),
        sa.Column('security_company_id', sa.Integer(), nullable=True),
        sa.Column('guard_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('en_route_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('arrived_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancellation_reason', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['security_company_id'], ['security_companies.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_emergency_calls_id'), 'emergency_calls', ['id'], unique=False)

    # --- Call Status History ---
    op.create_table('call_status_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('call_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('created', 'searching', 'offer_sent', 'accepted', 'en_route', 'arrived', 'completed', 'cancelled_by_user', 'cancelled_by_system', name='callstatus'), nullable=False),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('changed_by', sa.String(length=50), nullable=True),
        sa.Column('meta_info', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['call_id'], ['emergency_calls.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_call_status_history_id'), 'call_status_history', ['id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_call_status_history_id'), table_name='call_status_history')
    op.drop_table('call_status_history')
    op.drop_index(op.f('ix_emergency_calls_id'), table_name='emergency_calls')
    op.drop_table('emergency_calls')
    op.drop_index(op.f('ix_security_companies_id'), table_name='security_companies')
    op.drop_table('security_companies')
    op.drop_index(op.f('ix_user_devices_id'), table_name='user_devices')
    op.drop_table('user_devices')
    op.drop_index(op.f('ix_subscriptions_id'), table_name='subscriptions')
    op.drop_table('subscriptions')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')

    # Drop enums
    postgresql.ENUM(name='callstatus').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='subscriptionstatus').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='userstatus').drop(op.get_bind(), checkfirst=True)
