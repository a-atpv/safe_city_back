"""consolidate user token

Revision ID: 5579e2a55291
Revises: 004_consolidate_guard_token
Create Date: 2026-04-27 14:00:29.138158

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5579e2a55291'
down_revision: Union[str, None] = '004_consolidate_guard_token'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add fcm_token column to users table
    op.add_column('users', sa.Column('fcm_token', sa.String(500), nullable=True))

    # 2. Migrate data from user_devices to users
    # We take the latest active device token for each user
    op.execute("""
        UPDATE users
        SET fcm_token = (
            SELECT device_token
            FROM user_devices
            WHERE user_devices.user_id = users.id
            AND user_devices.is_active = true
            ORDER BY user_devices.updated_at DESC
            LIMIT 1
        )
    """)

    # 3. Drop user_devices table
    op.drop_index('ix_user_devices_id', table_name='user_devices')
    op.drop_table('user_devices')


def downgrade() -> None:
    # 1. Recreate user_devices table
    op.create_table(
        'user_devices',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('device_token', sa.String(500), nullable=True),
        sa.Column('device_type', sa.String(20), nullable=True),
        sa.Column('device_model', sa.String(100), nullable=True),
        sa.Column('app_version', sa.String(20), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_user_devices_id', 'user_devices', ['id'])

    # 2. Migrate data back
    op.execute("""
        INSERT INTO user_devices (user_id, device_token, is_active, created_at, updated_at)
        SELECT id, fcm_token, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM users
        WHERE fcm_token IS NOT NULL
    """)

    # 3. Drop fcm_token column from users
    op.drop_column('users', 'fcm_token')
