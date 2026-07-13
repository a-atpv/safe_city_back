"""split guard location freshness from liveness

Adds guards.current_accuracy (metres of the stored fix) and guards.last_seen
(liveness ping timestamp), so last_location_update can mean strictly "last
*accepted* position" — the signal dispatch and routing gate SOS on.

Revision ID: c3d8e0f21a94
Revises: a1f4c9d2e7b3
Create Date: 2026-07-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d8e0f21a94'
down_revision: Union[str, None] = 'a1f4c9d2e7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('guards', sa.Column('current_accuracy', sa.Float(), nullable=True))
    op.add_column('guards', sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('guards', 'last_seen')
    op.drop_column('guards', 'current_accuracy')
