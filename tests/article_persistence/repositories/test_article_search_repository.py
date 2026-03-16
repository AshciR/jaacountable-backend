"""Tests for the search_vector migration and trigger."""

import asyncpg

from src.article_persistence.models.domain import Article
from src.article_persistence.repositories.article_repository import ArticleRepository
from tests.article_persistence.utils import (
    get_article_search_vector,
    update_article_title,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _insert_article_with_text(
    conn: asyncpg.Connection,
    url: str,
    title: str,
    full_text: str,
    news_source_id: int = 1,
) -> Article:
    repo = ArticleRepository()
    article = Article(
        url=url,
        title=title,
        section="news",
        full_text=full_text,
        news_source_id=news_source_id,
    )
    return await repo.insert_article(conn, article)


# ---------------------------------------------------------------------------
# Migration / trigger tests
# ---------------------------------------------------------------------------

class TestSearchArticlesMigration:
    """Verify the search_vector column and trigger exist and work correctly."""

    async def test_search_vector_populated_on_insert(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: an article is inserted with title and full_text
        await _insert_article_with_text(
            db_connection,
            url="https://example.com/migration-test",
            title="Petrojam scandal investigation",
            full_text="The government launched a probe into Petrojam.",
        )

        # When: we check the search_vector column
        search_vector = await get_article_search_vector(
            db_connection, "https://example.com/migration-test"
        )

        # Then: search_vector is populated (not NULL)
        assert search_vector is not None

    async def test_search_vector_updated_on_title_change(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: an article is inserted
        article = await _insert_article_with_text(
            db_connection,
            url="https://example.com/trigger-test",
            title="Original title",
            full_text="Original content",
        )
        original_vector = await get_article_search_vector(
            db_connection, "https://example.com/trigger-test"
        )

        # When: the title is updated
        await update_article_title(
            db_connection, article.id, "Updated title with new keywords"
        )
        updated_vector = await get_article_search_vector(
            db_connection, "https://example.com/trigger-test"
        )

        # Then: search_vector changes to reflect the new title
        assert updated_vector != original_vector
