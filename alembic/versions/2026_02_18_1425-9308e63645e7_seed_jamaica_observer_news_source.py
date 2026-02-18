"""seed Jamaica Observer news source

Revision ID: 9308e63645e7
Revises: 2532338fa858
Create Date: 2026-02-18 14:25:28.695457

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9308e63645e7'
down_revision: Union[str, Sequence[str], None] = '2532338fa858'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        INSERT INTO news_sources (name, base_url, crawl_delay)
        VALUES ('Jamaica Observer', 'https://www.jamaicaobserver.com', 10)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
        DELETE FROM news_sources WHERE name = 'Jamaica Observer'
    """)
