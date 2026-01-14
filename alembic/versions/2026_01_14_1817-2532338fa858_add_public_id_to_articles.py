"""add public_id to articles

Revision ID: 2532338fa858
Revises: 4f51310f8125
Create Date: 2026-01-14 18:17:24.146740

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2532338fa858'
down_revision: Union[str, Sequence[str], None] = '4f51310f8125'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add public_id column with UUIDv4 default (universally available)
    op.execute("""
        ALTER TABLE articles
        ADD COLUMN public_id UUID DEFAULT gen_random_uuid()
    """)

    # Backfill existing articles with UUID values
    op.execute("""
        UPDATE articles
        SET public_id = gen_random_uuid()
        WHERE public_id IS NULL
    """)

    # Make column NOT NULL after backfill
    op.execute("""
        ALTER TABLE articles
        ALTER COLUMN public_id SET NOT NULL
    """)

    # Create unique index for fast lookups
    op.execute("""
        CREATE UNIQUE INDEX idx_articles_public_id
        ON articles(public_id)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop index first
    op.execute("DROP INDEX IF EXISTS idx_articles_public_id")

    # Drop column
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS public_id")
