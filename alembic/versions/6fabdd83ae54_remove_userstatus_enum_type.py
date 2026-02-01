"""remove_userstatus_enum_type

Revision ID: 6fabdd83ae54
Revises: 001_email_auth
Create Date: 2026-02-01 18:18:35.925871

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6fabdd83ae54'
down_revision: Union[str, None] = '001_email_auth'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Convert users.status to VARCHAR
    op.execute("ALTER TABLE users ALTER COLUMN status TYPE VARCHAR USING status::text")
    
    # 2. Drop the enum type if it exists
    op.execute("DROP TYPE IF EXISTS userstatus")

    # 3. Convert subscriptions.status to VARCHAR (just in case)
    # We use a safe approach: check if column exists and alter it. 
    # But standard SQL in alembic is usually direct. 
    # Let's assume subscriptions might be using 'subscriptionstatus' enum or varchar.
    # Casting to text and then varchar is safe for enums and varchars.
    op.execute("ALTER TABLE subscriptions ALTER COLUMN status TYPE VARCHAR USING status::text")
    
    # 4. Drop subscription enum type if exists
    op.execute("DROP TYPE IF EXISTS subscriptionstatus")


def downgrade() -> None:
    # Reverting is hard because we dropped the types. 
    # We would need to recreate them and cast back.
    
    # 1. Recreate userstatus type
    op.execute("CREATE TYPE userstatus AS ENUM ('active', 'inactive', 'blocked')")
    
    # 2. Cast users.status back
    op.execute("ALTER TABLE users ALTER COLUMN status TYPE userstatus USING status::userstatus")
    
    # 3. Recreate subscriptionstatus type
    op.execute("CREATE TYPE subscriptionstatus AS ENUM ('active', 'expired', 'cancelled', 'pending')")
    
    # 4. Cast subscriptions.status back
    op.execute("ALTER TABLE subscriptions ALTER COLUMN status TYPE subscriptionstatus USING status::subscriptionstatus")
