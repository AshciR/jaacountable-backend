"""add news_source_id to articles

Revision ID: a657a4df077c
Revises: 4f0ee70ba9e1
Create Date: 2025-11-24 21:27:17.584831

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a657a4df077c'
down_revision: Union[str, Sequence[str], None] = '4f0ee70ba9e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        ALTER TABLE articles
        ADD COLUMN news_source_id INTEGER NOT NULL
        REFERENCES news_sources(id) ON DELETE RESTRICT
    """)
    op.execute("CREATE INDEX idx_articles_news_source_id ON articles(news_source_id)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_articles_news_source_id")
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS news_source_id")
