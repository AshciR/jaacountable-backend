"""Utility functions for repository tests."""

import asyncpg

from src.article_persistence.models.domain import Article, ArticleEntity, Entity, NewsSource
from src.article_persistence.repositories.article_repository import ArticleRepository
from src.article_persistence.repositories.article_entity_repository import ArticleEntityRepository
from src.article_persistence.repositories.entity_repository import EntityRepository
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


async def create_test_entity(
    conn: asyncpg.Connection,
    name: str = "Test Entity",
    normalized_name: str = "test entity",
) -> Entity:
    """
    Helper function to create a test entity.

    Args:
        conn: Database connection
        name: Entity display name
        normalized_name: Normalized entity name (must be unique)

    Returns:
        Entity: The created entity with database-generated id
    """
    repository = EntityRepository()
    entity = Entity(
        name=name,
        normalized_name=normalized_name,
    )
    return await repository.insert_entity(conn, entity)


async def create_test_article_entity(
    conn: asyncpg.Connection,
    article_id: int,
    entity_id: int,
    classifier_type: str = "CORRUPTION",
) -> ArticleEntity:
    """
    Helper function to create a test article-entity association.

    Args:
        conn: Database connection
        article_id: ID of the article to link
        entity_id: ID of the entity to link
        classifier_type: Classifier that extracted this entity

    Returns:
        ArticleEntity: The created association with database-generated id
    """
    repository = ArticleEntityRepository()
    article_entity = ArticleEntity(
        article_id=article_id,
        entity_id=entity_id,
        classifier_type=classifier_type,
    )
    return await repository.link_article_to_entity(conn, article_entity)


async def delete_article(
    conn: asyncpg.Connection,
    article_id: int,
) -> None:
    """
    Helper function to delete an article by ID.

    Args:
        conn: Database connection
        article_id: ID of the article to delete
    """
    await conn.execute("DELETE FROM articles WHERE id = $1", article_id)


async def delete_entity(
    conn: asyncpg.Connection,
    entity_id: int,
) -> None:
    """
    Helper function to delete an entity by ID.

    Args:
        conn: Database connection
        entity_id: ID of the entity to delete
    """
    await conn.execute("DELETE FROM entities WHERE id = $1", entity_id)


async def check_record_exists(
    conn: asyncpg.Connection,
    table_name: str,
    record_id: int,
) -> bool:
    """
    Helper function to check if a record exists in a table.

    Args:
        conn: Database connection
        table_name: Name of the table to check
        record_id: ID of the record to check

    Returns:
        bool: True if record exists, False otherwise
    """
    count = await conn.fetchval(
        f"SELECT COUNT(*) FROM {table_name} WHERE id = $1",
        record_id,
    )
    return count > 0


async def count_articles_by_url(
    conn: asyncpg.Connection,
    url: str,
) -> int:
    """
    Count articles by URL.

    Args:
        conn: Database connection
        url: Article URL to search for

    Returns:
        int: Number of articles with this URL
    """
    return await conn.fetchval(
        "SELECT COUNT(*) FROM articles WHERE url = $1",
        url,
    )


async def count_article_entities(
    conn: asyncpg.Connection,
    article_id: int,
) -> int:
    """
    Count article-entity links for a given article.

    Args:
        conn: Database connection
        article_id: ID of the article

    Returns:
        int: Number of entity links for this article
    """
    return await conn.fetchval(
        "SELECT COUNT(*) FROM article_entities WHERE article_id = $1",
        article_id,
    )


async def count_entity_links_by_name(
    conn: asyncpg.Connection,
    article_id: int,
    normalized_name: str,
) -> int:
    """
    Count article-entity links for a specific entity by normalized name.

    Args:
        conn: Database connection
        article_id: ID of the article
        normalized_name: Normalized name of the entity

    Returns:
        int: Number of links between this article and entities with this normalized name
    """
    return await conn.fetchval(
        """
        SELECT COUNT(*) FROM article_entities
        WHERE article_id = $1 AND entity_id = (
            SELECT id FROM entities WHERE normalized_name = $2
        )
        """,
        article_id,
        normalized_name,
    )
