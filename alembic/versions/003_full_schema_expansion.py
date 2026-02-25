"""add_guards_admins_reviews_messaging_payments_settings_faq

Revision ID: 003_full_schema_expansion
Revises: 951d31a4e392
Create Date: 2026-02-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_full_schema_expansion'
down_revision: Union[str, None] = '951d31a4e392'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Modify existing tables ──

    # users: add city, language
    op.add_column('users', sa.Column('city', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('language', sa.String(5), server_default='ru', nullable=True))

    # security_companies: add details
    op.add_column('security_companies', sa.Column('city', sa.String(100), nullable=True))
    op.add_column('security_companies', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('security_companies', sa.Column('license_number', sa.String(100), nullable=True))
    op.add_column('security_companies', sa.Column('contract_start', sa.DateTime(timezone=True), nullable=True))
    op.add_column('security_companies', sa.Column('contract_end', sa.DateTime(timezone=True), nullable=True))

    # ── New table: guards ──
    op.create_table(
        'guards',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('security_company_id', sa.Integer(), sa.ForeignKey('security_companies.id'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('avatar_url', sa.String(500), nullable=True),
        sa.Column('employee_id', sa.String(50), nullable=True),
        sa.Column('status', sa.String(20), server_default='active'),
        sa.Column('is_online', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('is_on_call', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('current_latitude', sa.Float(), nullable=True),
        sa.Column('current_longitude', sa.Float(), nullable=True),
        sa.Column('last_location_update', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rating', sa.Float(), server_default='5.0'),
        sa.Column('total_reviews', sa.Integer(), server_default='0'),
        sa.Column('total_calls', sa.Integer(), server_default='0'),
        sa.Column('completed_calls', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_guards_id', 'guards', ['id'])
    op.create_index('ix_guards_email', 'guards', ['email'], unique=True)

    # ── emergency_calls: add guard FK + new columns ──
    # Change guard_id to FK (drop old column, add new one with FK)
    op.add_column('emergency_calls', sa.Column('estimated_arrival_minutes', sa.Integer(), nullable=True))
    op.add_column('emergency_calls', sa.Column('response_time_minutes', sa.Integer(), nullable=True))
    op.add_column('emergency_calls', sa.Column('user_message', sa.Text(), nullable=True))
    # Create FK constraint for existing guard_id column
    op.create_foreign_key(
        'fk_emergency_calls_guard_id',
        'emergency_calls', 'guards',
        ['guard_id'], ['id']
    )

    # ── New table: guard_devices ──
    op.create_table(
        'guard_devices',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('guard_id', sa.Integer(), sa.ForeignKey('guards.id'), nullable=False),
        sa.Column('device_token', sa.String(500), nullable=True),
        sa.Column('device_type', sa.String(20), nullable=True),
        sa.Column('device_model', sa.String(100), nullable=True),
        sa.Column('app_version', sa.String(20), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_guard_devices_id', 'guard_devices', ['id'])

    # ── New table: guard_shifts ──
    op.create_table(
        'guard_shifts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('guard_id', sa.Integer(), sa.ForeignKey('guards.id'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
    )
    op.create_index('ix_guard_shifts_id', 'guard_shifts', ['id'])

    # ── New table: guard_settings ──
    op.create_table(
        'guard_settings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('guard_id', sa.Integer(), sa.ForeignKey('guards.id'), nullable=False, unique=True),
        sa.Column('notifications_enabled', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('call_sound_enabled', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('vibration_enabled', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('language', sa.String(5), server_default='ru'),
        sa.Column('dark_theme_enabled', sa.Boolean(), server_default=sa.text('true')),
    )
    op.create_index('ix_guard_settings_id', 'guard_settings', ['id'])

    # ── New table: company_admins ──
    op.create_table(
        'company_admins',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('security_company_id', sa.Integer(), sa.ForeignKey('security_companies.id'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=True),
        sa.Column('role', sa.String(20), server_default='admin'),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_company_admins_id', 'company_admins', ['id'])
    op.create_index('ix_company_admins_email', 'company_admins', ['email'], unique=True)

    # ── New table: reviews ──
    op.create_table(
        'reviews',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('call_id', sa.Integer(), sa.ForeignKey('emergency_calls.id'), nullable=False, unique=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('guard_id', sa.Integer(), sa.ForeignKey('guards.id'), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_reviews_id', 'reviews', ['id'])

    # ── New table: call_reports ──
    op.create_table(
        'call_reports',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('call_id', sa.Integer(), sa.ForeignKey('emergency_calls.id'), nullable=False, unique=True),
        sa.Column('guard_id', sa.Integer(), sa.ForeignKey('guards.id'), nullable=False),
        sa.Column('report_text', sa.Text(), nullable=False),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_call_reports_id', 'call_reports', ['id'])

    # ── New table: call_messages ──
    op.create_table(
        'call_messages',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('call_id', sa.Integer(), sa.ForeignKey('emergency_calls.id'), nullable=False),
        sa.Column('sender_type', sa.String(10), nullable=False),
        sa.Column('sender_id', sa.Integer(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_call_messages_id', 'call_messages', ['id'])

    # ── New table: notifications ──
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('guard_id', sa.Integer(), sa.ForeignKey('guards.id'), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('data', sa.Text(), nullable=True),
        sa.Column('is_read', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_notifications_id', 'notifications', ['id'])

    # ── New table: payments ──
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('subscription_id', sa.Integer(), sa.ForeignKey('subscriptions.id'), nullable=True),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), server_default='KZT'),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('payment_method', sa.String(50), nullable=True),
        sa.Column('provider_transaction_id', sa.String(255), nullable=True),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_payments_id', 'payments', ['id'])

    # ── New table: user_settings ──
    op.create_table(
        'user_settings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('notifications_enabled', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('call_sound_enabled', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('vibration_enabled', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('language', sa.String(5), server_default='ru'),
        sa.Column('dark_theme_enabled', sa.Boolean(), server_default=sa.text('true')),
    )
    op.create_index('ix_user_settings_id', 'user_settings', ['id'])

    # ── New table: faq_categories ──
    op.create_table(
        'faq_categories',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('target', sa.String(20), server_default='both'),
        sa.Column('order', sa.Integer(), server_default='0'),
    )
    op.create_index('ix_faq_categories_id', 'faq_categories', ['id'])

    # ── New table: faq_items ──
    op.create_table(
        'faq_items',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('faq_categories.id'), nullable=False),
        sa.Column('question', sa.String(500), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('target', sa.String(20), server_default='both'),
        sa.Column('order', sa.Integer(), server_default='0'),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
    )
    op.create_index('ix_faq_items_id', 'faq_items', ['id'])


def downgrade() -> None:
    op.drop_table('faq_items')
    op.drop_table('faq_categories')
    op.drop_table('user_settings')
    op.drop_table('payments')
    op.drop_table('notifications')
    op.drop_table('call_messages')
    op.drop_table('call_reports')
    op.drop_table('reviews')
    op.drop_table('company_admins')
    op.drop_table('guard_settings')
    op.drop_table('guard_shifts')
    op.drop_table('guard_devices')

    op.drop_constraint('fk_emergency_calls_guard_id', 'emergency_calls', type_='foreignkey')
    op.drop_column('emergency_calls', 'user_message')
    op.drop_column('emergency_calls', 'response_time_minutes')
    op.drop_column('emergency_calls', 'estimated_arrival_minutes')

    op.drop_table('guards')

    op.drop_column('security_companies', 'contract_end')
    op.drop_column('security_companies', 'contract_start')
    op.drop_column('security_companies', 'license_number')
    op.drop_column('security_companies', 'description')
    op.drop_column('security_companies', 'city')

    op.drop_column('users', 'language')
    op.drop_column('users', 'city')
