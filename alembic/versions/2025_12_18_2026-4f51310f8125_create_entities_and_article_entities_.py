"""create entities and article_entities tables

Revision ID: 4f51310f8125
Revises: a657a4df077c
Create Date: 2025-12-18 20:26:39.311579

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f51310f8125'
down_revision: Union[str, Sequence[str], None] = 'a657a4df077c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create entities table
    op.execute("""
        CREATE TABLE entities (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # Create unique constraint on normalized_name for deduplication
    op.execute("ALTER TABLE entities ADD CONSTRAINT uq_entities_normalized_name UNIQUE (normalized_name)")

    # Create index on name for lookups
    op.execute("CREATE INDEX idx_entities_name ON entities(name)")

    # Create article_entities junction table
    op.execute("""
        CREATE TABLE article_entities (
            id SERIAL PRIMARY KEY,
            article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            classifier_type TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # Create unique constraint to prevent duplicate associations
    op.execute("ALTER TABLE article_entities ADD CONSTRAINT uq_article_entities_article_entity UNIQUE (article_id, entity_id)")

    # Create indexes for foreign key lookups
    op.execute("CREATE INDEX idx_article_entities_article_id ON article_entities(article_id)")
    op.execute("CREATE INDEX idx_article_entities_entity_id ON article_entities(entity_id)")


def downgrade() -> None:
    """Downgrade schema."""
    # Drop article_entities table and its indexes
    op.execute("DROP INDEX IF EXISTS idx_article_entities_entity_id")
    op.execute("DROP INDEX IF EXISTS idx_article_entities_article_id")
    op.execute("DROP TABLE IF EXISTS article_entities")

    # Drop entities table and its index
    op.execute("DROP INDEX IF EXISTS idx_entities_name")
    op.execute("DROP TABLE IF EXISTS entities")
