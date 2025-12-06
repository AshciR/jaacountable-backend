"""Utility functions for repository tests."""

import asyncpg

from src.article_persistence.models.domain import Article, NewsSource
from src.article_persistence.repositories.article_repository import ArticleRepository
from src.article_persistence.repositories.news_source_repository import NewsSourceRepository


async def create_test_news_source(
    conn: asyncpg.Connection,
    name: str = "Test News Source",
    base_url: str = "https://test-news.com",
    crawl_delay: int = 10,
) -> NewsSource:
    """
    Helper function to create a test news source for article tests.

    Args:
        conn: Database connection
        name: News source name (must be unique)
        base_url: Base URL for the news source
        crawl_delay: Crawl delay in seconds

    Returns:
        NewsSource: The created news source with database-generated id
    """
    repository = NewsSourceRepository()
    news_source = NewsSource(
        name=name,
        base_url=base_url,
        crawl_delay=crawl_delay,
    )
    return await repository.insert_news_source(conn, news_source)


async def create_test_article(
    db_connection: asyncpg.Connection,
    url: str = "https://example.com/test-article",
    title: str = "Test Article",
    section: str = "news",
    news_source_id: int = 1,
) -> Article:
    """
    Helper function to create a test article for classification tests.

    Args:
        db_connection: Database connection
        url: Article URL (must be unique)
        title: Article title
        section: Article section
        news_source_id: ID of the news source (defaults to 1, the seeded Jamaica Gleaner)

    Returns:
        Article: The created article with database-generated id
    """
    article_repo = ArticleRepository()
    article = Article(
        url=url,
        title=title,
        section=section,
        news_source_id=news_source_id,
    )
    return await article_repo.insert_article(db_connection, article)
