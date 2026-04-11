"""decode html entities in article titles

Revision ID: 18571ff9ca84
Revises: 471d8bf395eb
Create Date: 2026-04-10 22:33:40.813825

"""
import html
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18571ff9ca84'
down_revision: Union[str, Sequence[str], None] = '471d8bf395eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Decode HTML entities in article titles stored verbatim from RSS feeds."""
    conn = op.get_bind()

    rows = conn.execute(
        sa.text("SELECT id, title FROM articles WHERE title LIKE '%&%'")
    ).fetchall()

    for row_id, title in rows:
        decoded = html.unescape(title)
        if decoded != title:
            conn.execute(
                sa.text("UPDATE articles SET title = :title WHERE id = :id"),
                {"title": decoded, "id": row_id},
            )


def downgrade() -> None:
    """No-op — decoded titles cannot be re-encoded without the original values."""
    pass
