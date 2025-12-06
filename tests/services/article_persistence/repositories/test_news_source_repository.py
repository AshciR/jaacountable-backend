"""Tests for NewsSourceRepository."""

import asyncpg
import pytest
from datetime import datetime, timedelta, timezone

from src.article_persistence.repositories.news_source_repository import NewsSourceRepository
from src.article_persistence.models.domain import NewsSource


class TestInsertNewsSourceHappyPath:
    """Happy path tests for insert_news_source."""

    async def test_insert_news_source_success(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: a valid news source with all fields populated
        news_source = NewsSource(
            name="Test News Source",
            base_url="https://test-news.com",
            crawl_delay=15,
            is_active=True,
            last_scraped_at=datetime(2025, 11, 20, 12, 0, 0, tzinfo=timezone.utc),
        )
        repository = NewsSourceRepository()

        # When: the news source is inserted
        result = await repository.insert_news_source(db_connection, news_source)

        # Then: the returned news source has a database-generated id and matching fields
        assert result.id is not None
        assert result.name == "Test News Source"
        assert result.base_url == "https://test-news.com"
        assert result.crawl_delay == 15
        assert result.is_active is True
        assert result.last_scraped_at == datetime(2025, 11, 20, 12, 0, 0, tzinfo=timezone.utc)
        assert result.created_at is not None

    async def test_insert_news_source_with_minimal_fields(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: a news source with only required fields (name, base_url)
        news_source = NewsSource(
            name="Minimal News Source",
            base_url="https://minimal-news.com",
        )
        repository = NewsSourceRepository()

        # When: the news source is inserted
        result = await repository.insert_news_source(db_connection, news_source)

        # Then: returns news source with id, defaults applied
        assert result.id is not None
        assert result.name == "Minimal News Source"
        assert result.base_url == "https://minimal-news.com"
        assert result.crawl_delay == 10  # default value
        assert result.is_active is True  # default value
        assert result.last_scraped_at is None
        assert result.created_at is not None

    async def test_insert_news_source_strips_whitespace(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: a news source with whitespace-padded fields
        news_source = NewsSource(
            name="  Whitespace News  ",
            base_url="  https://whitespace-news.com  ",
        )
        repository = NewsSourceRepository()

        # When: the news source is inserted
        result = await repository.insert_news_source(db_connection, news_source)

        # Then: returns news source with trimmed fields (Pydantic validation)
        assert result.id is not None
        assert result.name == "Whitespace News"
        assert result.base_url == "https://whitespace-news.com"

    async def test_insert_news_source_defaults_created_at(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: a news source without explicit created_at
        before_insert = datetime.now(timezone.utc)
        news_source = NewsSource(
            name="Default Created At News",
            base_url="https://default-created-at.com",
        )
        repository = NewsSourceRepository()

        # When: the news source is inserted
        result = await repository.insert_news_source(db_connection, news_source)
        after_insert = datetime.now(timezone.utc)

        # Then: returns news source with created_at close to current time
        assert result.id is not None
        assert result.created_at is not None
        # Allow 1 second tolerance for test execution time
        assert before_insert - timedelta(seconds=1) <= result.created_at <= after_insert + timedelta(seconds=1)

    async def test_insert_news_source_with_custom_created_at(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: a news source with explicit created_at value
        custom_created_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        news_source = NewsSource(
            name="Custom Created At News",
            base_url="https://custom-created-at.com",
            created_at=custom_created_at,
        )
        repository = NewsSourceRepository()

        # When: the news source is inserted
        result = await repository.insert_news_source(db_connection, news_source)

        # Then: returns news source with the custom created_at preserved
        assert result.id is not None
        assert result.created_at == custom_created_at

    async def test_insert_news_source_inactive(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: a news source with is_active set to False
        news_source = NewsSource(
            name="Inactive News Source",
            base_url="https://inactive-news.com",
            is_active=False,
        )
        repository = NewsSourceRepository()

        # When: the news source is inserted
        result = await repository.insert_news_source(db_connection, news_source)

        # Then: returns news source with is_active as False
        assert result.id is not None
        assert result.is_active is False


class TestInsertNewsSourceDatabaseConstraints:
    """Database constraint tests for insert_news_source."""

    async def test_duplicate_name_raises_unique_violation(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: a news source already exists with a specific name
        repository = NewsSourceRepository()
        first_source = NewsSource(
            name="Duplicate Test News",
            base_url="https://first-news.com",
        )
        await repository.insert_news_source(db_connection, first_source)

        # When: another news source with the same name is inserted
        second_source = NewsSource(
            name="Duplicate Test News",
            base_url="https://second-news.com",
        )

        # Then: raises asyncpg.UniqueViolationError
        with pytest.raises(asyncpg.UniqueViolationError):
            await repository.insert_news_source(db_connection, second_source)

    async def test_same_name_different_url_fails(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: a news source exists with name X
        repository = NewsSourceRepository()
        first_source = NewsSource(
            name="Name Unique Test",
            base_url="https://url-one.com",
        )
        await repository.insert_news_source(db_connection, first_source)

        # When: another news source with same name X but different URL is inserted
        second_source = NewsSource(
            name="Name Unique Test",
            base_url="https://url-two.com",
        )

        # Then: raises UniqueViolationError (name uniqueness is enforced)
        with pytest.raises(asyncpg.UniqueViolationError):
            await repository.insert_news_source(db_connection, second_source)


class TestInsertNewsSourceEdgeCases:
    """Edge case tests for insert_news_source."""

    async def test_with_unicode_name(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: a news source with Unicode characters in name
        unicode_name = "Jamaica Gleaner — 日本語ニュース"
        news_source = NewsSource(
            name=unicode_name,
            base_url="https://unicode-news.com",
        )
        repository = NewsSourceRepository()

        # When: the news source is inserted
        result = await repository.insert_news_source(db_connection, news_source)

        # Then: returns news source with Unicode name preserved
        assert result.id is not None
        assert result.name == unicode_name


    async def test_with_zero_crawl_delay(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: a news source with zero crawl_delay (no delay)
        news_source = NewsSource(
            name="Zero Delay News",
            base_url="https://zero-delay.com",
            crawl_delay=0,
        )
        repository = NewsSourceRepository()

        # When: the news source is inserted
        result = await repository.insert_news_source(db_connection, news_source)

        # Then: successfully inserts with zero delay (valid)
        assert result.id is not None
        assert result.crawl_delay == 0

    async def test_with_large_crawl_delay(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: a news source with a very large crawl_delay
        news_source = NewsSource(
            name="Large Delay News",
            base_url="https://large-delay.com",
            crawl_delay=3600,  # 1 hour
        )
        repository = NewsSourceRepository()

        # When: the news source is inserted
        result = await repository.insert_news_source(db_connection, news_source)

        # Then: successfully inserts with large delay
        assert result.id is not None
        assert result.crawl_delay == 3600

