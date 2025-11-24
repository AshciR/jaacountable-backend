"""create news_sources table

Revision ID: 4f0ee70ba9e1
Revises: 6d8635339162
Create Date: 2025-11-24 08:55:49.881658

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f0ee70ba9e1'
down_revision: Union[str, Sequence[str], None] = '6d8635339162'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE TABLE news_sources (
            id SERIAL PRIMARY KEY,
            name VARCHAR NOT NULL UNIQUE,
            base_url VARCHAR NOT NULL,
            crawl_delay INTEGER NOT NULL DEFAULT 10,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            last_scraped_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_news_sources_is_active ON news_sources(is_active)")

    # Seed Jamaica Gleaner as the initial news source
    op.execute("""
        INSERT INTO news_sources (name, base_url, crawl_delay)
        VALUES ('Jamaica Gleaner', 'https://jamaica-gleaner.com', 10)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_news_sources_is_active")
    op.execute("DROP TABLE IF EXISTS news_sources")
