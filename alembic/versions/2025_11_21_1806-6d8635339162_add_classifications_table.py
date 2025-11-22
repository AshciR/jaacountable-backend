"""add classifications table

Revision ID: 6d8635339162
Revises: 59f8e37f0c42
Create Date: 2025-11-21 18:06:49.921266

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6d8635339162'
down_revision: Union[str, Sequence[str], None] = '59f8e37f0c42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE TABLE classifications (
            id SERIAL PRIMARY KEY,
            article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            classifier_type TEXT NOT NULL,
            confidence_score FLOAT NOT NULL,
            reasoning TEXT,
            classified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            model_name TEXT NOT NULL,
            is_verified BOOLEAN NOT NULL DEFAULT FALSE,
            verified_at TIMESTAMPTZ,
            verified_by TEXT
        )
    """)
    op.execute("CREATE INDEX idx_classifications_article_id ON classifications(article_id)")
    op.execute("CREATE INDEX idx_classifications_classifier_type ON classifications(classifier_type)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_classifications_classifier_type")
    op.execute("DROP INDEX IF EXISTS idx_classifications_article_id")
    op.execute("DROP TABLE IF EXISTS classifications")
