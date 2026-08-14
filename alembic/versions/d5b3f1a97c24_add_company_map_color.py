"""add security_companies.map_color

The global admin map draws every company in its own colour, and every ГБР unit
of that company gets a border in it. Existing companies are backfilled from the
same palette the API assigns to new ones (kept in
app/services/global_admin.py — duplicated here on purpose, so a later edit of
the palette can't rewrite what this migration already wrote).

Revision ID: d5b3f1a97c24
Revises: f2a7c9d1e3b8
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5b3f1a97c24'
down_revision: Union[str, None] = 'f2a7c9d1e3b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PALETTE = (
    '#4F8CFF', '#2ECC71', '#F5A623', '#B57BFF',
    '#00D2D3', '#FF7AC8', '#A3E635', '#C68B59',
)


def upgrade() -> None:
    op.add_column('security_companies', sa.Column('map_color', sa.String(length=7), nullable=True))

    # Backfill deterministically by id, so colours stay stable across environments
    # that share the same data (prod → test copies).
    # mod(id, n) rather than id % n: a bare '%' in the statement is ambiguous for
    # DBAPI drivers that use pyformat parameters.
    colors = ','.join(f"'{c}'" for c in PALETTE)
    op.execute(
        f"UPDATE security_companies "
        f"SET map_color = (ARRAY[{colors}])[mod(id, {len(PALETTE)}) + 1] "
        f"WHERE map_color IS NULL"
    )


def downgrade() -> None:
    op.drop_column('security_companies', 'map_color')
