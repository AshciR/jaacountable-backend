"""Tests for ArticleRepository."""

import asyncpg
from datetime import datetime

from src.db.repositories.article_repository import ArticleRepository
from src.db.models.domain import Article


async def test_insert_article_success(
    db_connection: asyncpg.Connection,
):
    # Given: a valid article and repository
    article = Article(
        url="https://example.com/test-article",
        title="Test Article",
        section="news",
        published_date=datetime(2025, 11, 15),
        full_text="Article content here",
    )
    repository = ArticleRepository()

    # When: the article is inserted
    result = await repository.insert_article(db_connection, article)

    # Then: the returned article has a database-generated id and matching fields
    assert result.id is not None
    assert result.url == article.url
    assert result.title == article.title
    assert result.section == article.section
    assert result.published_date == article.published_date
    assert result.full_text == article.full_text
