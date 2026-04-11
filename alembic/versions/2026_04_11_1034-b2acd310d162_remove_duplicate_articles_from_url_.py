"""remove duplicate articles from url normalisation

Revision ID: b2acd310d162
Revises: 18571ff9ca84
Create Date: 2026-04-11 10:34:27.356669

"""
from typing import Sequence, Union
from urllib.parse import unquote, urlparse, urlunparse

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2acd310d162'
down_revision: Union[str, Sequence[str], None] = '18571ff9ca84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_url(url: str) -> str:
    decoded = unquote(url)
    parsed = urlparse(decoded)
    path = parsed.path
    if path.startswith("/index.php/"):
        path = path[len("/index.php"):]
    return urlunparse(parsed._replace(path=path))


def upgrade() -> None:
    """Remove duplicate articles caused by non-canonical index%2ephp / index.php URLs.

    For each non-canonical article:
    - If a canonical-URL article already exists: delete the duplicate (CASCADE removes
      any related classifications and article_entities rows).
    - If no canonical article exists: update the URL to its canonical form.
    """
    conn = op.get_bind()

    rows = conn.execute(
        sa.text(
            "SELECT id, url FROM articles "
            "WHERE url LIKE '%index%2ephp%' OR url LIKE '%/index.php/%'"
        )
    ).fetchall()

    for row_id, url in rows:
        canonical = _normalize_url(url)
        if canonical == url:
            continue

        existing = conn.execute(
            sa.text("SELECT id FROM articles WHERE url = :url"),
            {"url": canonical},
        ).fetchone()

        if existing:
            conn.execute(
                sa.text("DELETE FROM articles WHERE id = :id"),
                {"id": row_id},
            )
        else:
            conn.execute(
                sa.text("UPDATE articles SET url = :url WHERE id = :id"),
                {"url": canonical, "id": row_id},
            )


def downgrade() -> None:
    """No-op — deleted duplicates cannot be restored."""
    pass
