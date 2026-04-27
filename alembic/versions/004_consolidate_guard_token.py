"""consolidate_guard_token

Revision ID: 004_consolidate_guard_token
Revises: 003_full_schema_expansion
Create Date: 2026-04-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004_consolidate_guard_token'
down_revision: Union[str, None] = '003_full_schema_expansion'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add fcm_token column to guards table
    op.add_column('guards', sa.Column('fcm_token', sa.String(500), nullable=True))

    # 2. Migrate data from guard_devices to guards
    # We take the latest active device token for each guard
    # Using raw SQL for the migration
    op.execute("""
        UPDATE guards
        SET fcm_token = (
            SELECT device_token
            FROM guard_devices
            WHERE guard_devices.guard_id = guards.id
            AND guard_devices.is_active = true
            ORDER BY guard_devices.updated_at DESC
            LIMIT 1
        )
    """)

    # 3. Drop guard_devices table
    op.drop_index('ix_guard_devices_id', table_name='guard_devices')
    op.drop_table('guard_devices')


def downgrade() -> None:
    # 1. Recreate guard_devices table
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

    # 2. Migrate data back (optional, might not be perfectly accurate)
    op.execute("""
        INSERT INTO guard_devices (guard_id, device_token, is_active, created_at, updated_at)
        SELECT id, fcm_token, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM guards
        WHERE fcm_token IS NOT NULL
    """)

    # 3. Drop fcm_token column from guards
    op.drop_column('guards', 'fcm_token')
