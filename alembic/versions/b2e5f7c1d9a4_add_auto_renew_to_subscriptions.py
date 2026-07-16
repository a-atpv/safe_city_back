"""add auto_renew to subscriptions

Revision ID: b2e5f7c1d9a4
Revises: c3d8e0f21a94
Create Date: 2026-07-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2e5f7c1d9a4'
down_revision: Union[str, None] = 'c3d8e0f21a94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Default False is safe for existing rows: no sub auto-renews until a fresh
    # recurring payment sets it True, so nothing starts charging on deploy.
    op.add_column(
        'subscriptions',
        sa.Column('auto_renew', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('subscriptions', 'auto_renew')
