"""merge_heads

Revision ID: 951d31a4e392
Revises: 002_add_role_column, 6fabdd83ae54
Create Date: 2026-02-02 16:02:48.125525

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '951d31a4e392'
down_revision: Union[str, None] = ('002_add_role_column', '6fabdd83ae54')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
