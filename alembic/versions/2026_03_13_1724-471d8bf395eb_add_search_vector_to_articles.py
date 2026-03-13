"""add search vector to articles

Revision ID: 471d8bf395eb
Revises: 9308e63645e7
Create Date: 2026-03-13 17:24:28.701054

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '471d8bf395eb'
down_revision: Union[str, Sequence[str], None] = '9308e63645e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE articles ADD COLUMN search_vector tsvector")

    op.execute(
        "CREATE INDEX idx_articles_search_vector ON articles USING GIN (search_vector)"
    )

    op.execute("""
        CREATE FUNCTION articles_search_vector_update() RETURNS trigger AS $$
        BEGIN
          NEW.search_vector :=
            setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(NEW.full_text, '')), 'B');
          RETURN NEW;
        END
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER articles_search_vector_trigger
        BEFORE INSERT OR UPDATE ON articles
        FOR EACH ROW EXECUTE FUNCTION articles_search_vector_update()
    """)

    op.execute("""
        UPDATE articles SET search_vector =
          setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
          setweight(to_tsvector('english', coalesce(full_text, '')), 'B')
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP TRIGGER IF EXISTS articles_search_vector_trigger ON articles"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS articles_search_vector_update()"
    )
    op.execute(
        "DROP INDEX IF EXISTS idx_articles_search_vector"
    )
    op.execute(
        "ALTER TABLE articles DROP COLUMN IF EXISTS search_vector"
    )
