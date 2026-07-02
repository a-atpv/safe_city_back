"""add robokassa fields to payments

Revision ID: a1f4c9d2e7b3
Revises: 8960007f71a5
Create Date: 2026-07-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f4c9d2e7b3'
down_revision: Union[str, None] = '8960007f71a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payments', sa.Column('plan_type', sa.String(length=50), nullable=True))
    op.add_column('payments', sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        'payments',
        sa.Column('is_recurring', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column('payments', sa.Column('parent_inv_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('payments', 'parent_inv_id')
    op.drop_column('payments', 'is_recurring')
    op.drop_column('payments', 'paid_at')
    op.drop_column('payments', 'plan_type')
