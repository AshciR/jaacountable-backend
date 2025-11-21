"""convert timestamps to timestamptz for utc support

Revision ID: 59f8e37f0c42
Revises: 399757bac0a6
Create Date: 2025-11-20 20:18:33.085181

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '59f8e37f0c42'
down_revision: Union[str, Sequence[str], None] = '399757bac0a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        ALTER TABLE articles
        ALTER COLUMN published_date TYPE TIMESTAMPTZ;
    """)
    op.execute("""
        ALTER TABLE articles
        ALTER COLUMN fetched_at TYPE TIMESTAMPTZ;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
        ALTER TABLE articles
        ALTER COLUMN published_date TYPE TIMESTAMP;
    """)
    op.execute("""
        ALTER TABLE articles
        ALTER COLUMN fetched_at TYPE TIMESTAMP;
    """)
