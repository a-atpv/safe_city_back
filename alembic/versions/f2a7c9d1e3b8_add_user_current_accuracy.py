"""add users.current_accuracy

Adds users.current_accuracy (metres of the stored fix) so the user-side
location pipeline can reject jitter — a barely-there move reported by a *less*
accurate fix — the same way the guard side already does. Mirrors the guard
current_accuracy column added in c3d8e0f21a94.

Revision ID: f2a7c9d1e3b8
Revises: b2e5f7c1d9a4
Create Date: 2026-07-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a7c9d1e3b8'
down_revision: Union[str, None] = 'b2e5f7c1d9a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('current_accuracy', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'current_accuracy')
