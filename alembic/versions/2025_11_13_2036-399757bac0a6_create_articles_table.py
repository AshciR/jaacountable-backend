"""create articles table

Revision ID: 399757bac0a6
Revises: 
Create Date: 2025-11-13 20:36:07.312299

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '399757bac0a6'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create articles table
    op.execute("""
        CREATE TABLE articles (
            id SERIAL PRIMARY KEY,
            url VARCHAR UNIQUE NOT NULL,
            title VARCHAR NOT NULL,
            section VARCHAR NOT NULL,
            published_date TIMESTAMP,
            fetched_at TIMESTAMP NOT NULL DEFAULT NOW(),
            full_text TEXT
        )
    """)

    # Create indexes for performance
    op.execute("CREATE INDEX idx_articles_url ON articles(url)")
    op.execute("CREATE INDEX idx_articles_published_date ON articles(published_date)")


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes first
    op.execute("DROP INDEX IF EXISTS idx_articles_published_date")
    op.execute("DROP INDEX IF EXISTS idx_articles_url")

    # Drop table
    op.execute("DROP TABLE IF EXISTS articles")
