"""Unit tests for ArticleDiscoveryService."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import asyncpg
import pytest
import pytest_asyncio

from src.article_discovery.models import DiscoveredArticle
from src.article_discovery.service import ArticleDiscoveryService
from src.article_persistence.models.domain import NewsSource
from src.article_persistence.repositories.news_source_repository import (
    NewsSourceRepository,
)


@pytest_asyncio.fixture
async def test_news_source(db_connection: asyncpg.Connection):
    """Create a test news source in the database (Jamaica Observer)."""
    news_source = NewsSource(
        name="Jamaica Observer",
        base_url="https://jamaicaobserver.com",
        crawl_delay=10,
        is_active=True,
        last_scraped_at=None,
        created_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    )

    repository = NewsSourceRepository()
    inserted = await repository.insert_news_source(db_connection, news_source)
    return inserted


@pytest.fixture
def sample_discovered_articles(test_news_source: NewsSource):
    """Sample discovered articles for testing."""
    return [
        DiscoveredArticle(
            url="https://jamaicaobserver.com/news/2024/01/01/sample-article-1",
            news_source_id=test_news_source.id,
            section="news",
            discovered_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            title="Sample Article 1",
            published_date=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        ),
        DiscoveredArticle(
            url="https://jamaicaobserver.com/news/2024/01/02/sample-article-2",
            news_source_id=test_news_source.id,
            section="news",
            discovered_at=datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
            title="Sample Article 2",
            published_date=datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc),
        ),
    ]


@pytest.fixture
def mock_discoverer():
    """Mock article discoverer for testing."""
    discoverer = AsyncMock()
    discoverer.discover = AsyncMock()
    return discoverer


@pytest.fixture
def news_source_repository():
    """Real news source repository for testing."""
    return NewsSourceRepository()


@pytest.fixture
def service(mock_discoverer, news_source_repository):
    """ArticleDiscoveryService instance for testing."""
    return ArticleDiscoveryService(
        discoverer=mock_discoverer,
        news_source_repository=news_source_repository,
    )


class TestArticleDiscoveryServiceHappyPath:
    """Test ArticleDiscoveryService happy path scenarios."""

    @pytest.mark.asyncio
    async def test_discoverer_returns_articles_successfully(
            self,
            service: ArticleDiscoveryService,
            mock_discoverer,
            db_connection: asyncpg.Connection,
            test_news_source: NewsSource,
            sample_discovered_articles,
    ):
        """
        Given: A service with a discoverer that returns articles
        When: discover() is called
        Then: Articles are returned successfully
        """
        # Given
        mock_discoverer.discover.return_value = sample_discovered_articles

        # When
        result = await service.discover(
            conn=db_connection, news_source_id=test_news_source.id
        )

        # Then
        assert result == sample_discovered_articles
        mock_discoverer.discover.assert_called_once_with(test_news_source.id)

    @pytest.mark.asyncio
    async def test_last_scraped_at_updated_in_database(
            self,
            service: ArticleDiscoveryService,
            mock_discoverer,
            db_connection: asyncpg.Connection,
            test_news_source: NewsSource,
            sample_discovered_articles,
    ):
        """
        Given: A service that discovers articles
        When: discover() is called successfully
        Then: last_scraped_at is updated in the database
        """
        # Given
        mock_discoverer.discover.return_value = sample_discovered_articles
        assert test_news_source.last_scraped_at is None  # Initially None

        # When
        await service.discover(
            conn=db_connection, news_source_id=test_news_source.id
        )

        # Then: Verify last_scraped_at was updated by querying database
        updated_source = await db_connection.fetchrow(
            "SELECT * FROM news_sources WHERE id = $1", test_news_source.id
        )
        assert updated_source["last_scraped_at"] is not None
        assert isinstance(updated_source["last_scraped_at"], datetime)


class TestArticleDiscoveryServiceValidation:
    """Test ArticleDiscoveryService validation scenarios."""

    @pytest.mark.asyncio
    async def test_invalid_news_source_id_raises_value_error(
            self,
            service: ArticleDiscoveryService,
            mock_discoverer,
            db_connection: asyncpg.Connection,
    ):
        """
        Given: A discoverer that raises ValueError for invalid news_source_id
        When: discover() is called with invalid news_source_id
        Then: ValueError is propagated as-is (not wrapped)
        """
        # Given
        mock_discoverer.discover.side_effect = ValueError(
            "News source ID must be positive"
        )

        # When / Then
        with pytest.raises(ValueError, match="News source ID must be positive"):
            await service.discover(conn=db_connection, news_source_id=0)

    @pytest.mark.asyncio
    async def test_value_error_from_discoverer_propagated_as_is(
            self,
            service: ArticleDiscoveryService,
            mock_discoverer,
            db_connection: asyncpg.Connection,
            test_news_source: NewsSource,
    ):
        """
        Given: A discoverer that raises ValueError
        When: discover() is called
        Then: ValueError is re-raised without wrapping
        """
        # Given
        error_message = "Invalid configuration"
        mock_discoverer.discover.side_effect = ValueError(error_message)

        # When / Then
        with pytest.raises(ValueError, match=error_message):
            await service.discover(
                conn=db_connection, news_source_id=test_news_source.id
            )


class TestArticleDiscoveryServiceErrorHandling:
    """Test ArticleDiscoveryService error handling scenarios."""

    @pytest.mark.asyncio
    async def test_discoverer_runtime_error_wrapped_and_reraised(
            self,
            service: ArticleDiscoveryService,
            mock_discoverer,
            db_connection: asyncpg.Connection,
            test_news_source: NewsSource,
    ):
        """
        Given: A discoverer that raises RuntimeError
        When: discover() is called
        Then: RuntimeError is wrapped in new RuntimeError with context
        """
        # Given
        original_error = RuntimeError("Network failure")
        mock_discoverer.discover.side_effect = original_error

        # When / Then
        with pytest.raises(
                RuntimeError, match=f"Discovery failed for source {test_news_source.id}"
        ):
            await service.discover(
                conn=db_connection, news_source_id=test_news_source.id
            )

    @pytest.mark.asyncio
    async def test_discoverer_generic_exception_wrapped_in_runtime_error(
            self,
            service: ArticleDiscoveryService,
            mock_discoverer,
            db_connection: asyncpg.Connection,
            test_news_source: NewsSource,
    ):
        """
        Given: A discoverer that raises a generic Exception
        When: discover() is called
        Then: Exception is wrapped in RuntimeError
        """
        # Given
        original_error = Exception("Unexpected error")
        mock_discoverer.discover.side_effect = original_error

        # When / Then
        with pytest.raises(
                RuntimeError, match=f"Discovery failed for source {test_news_source.id}"
        ):
            await service.discover(
                conn=db_connection, news_source_id=test_news_source.id
            )

    @pytest.mark.asyncio
    async def test_error_message_includes_news_source_id(
            self,
            service: ArticleDiscoveryService,
            mock_discoverer,
            db_connection: asyncpg.Connection,
            test_news_source: NewsSource,
    ):
        """
        Given: A discoverer that raises an exception
        When: discover() is called with specific news_source_id
        Then: Wrapped error message includes the news_source_id
        """
        # Given
        mock_discoverer.discover.side_effect = Exception("Failed")

        # When / Then
        with pytest.raises(RuntimeError) as exc_info:
            await service.discover(
                conn=db_connection, news_source_id=test_news_source.id
            )

        assert f"source {test_news_source.id}" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_original_exception_preserved_in_chain(
            self,
            service: ArticleDiscoveryService,
            mock_discoverer,
            db_connection: asyncpg.Connection,
            test_news_source: NewsSource,
    ):
        """
        Given: A discoverer that raises an exception
        When: discover() is called and exception is wrapped
        Then: Original exception is preserved in __cause__
        """
        # Given
        original_error = Exception("Original error")
        mock_discoverer.discover.side_effect = original_error

        # When / Then
        with pytest.raises(RuntimeError) as exc_info:
            await service.discover(
                conn=db_connection, news_source_id=test_news_source.id
            )

        assert exc_info.value.__cause__ is original_error


class TestArticleDiscoveryServiceEdgeCases:
    """Test ArticleDiscoveryService edge case scenarios."""

    @pytest.mark.asyncio
    async def test_discoverer_returns_empty_list(
            self,
            service: ArticleDiscoveryService,
            mock_discoverer,
            db_connection: asyncpg.Connection,
            test_news_source: NewsSource,
    ):
        """
        Given: A discoverer that returns an empty list
        When: discover() is called
        Then: Empty list is returned and repository is still updated
        """
        # Given
        mock_discoverer.discover.return_value = []

        # When
        result = await service.discover(
            conn=db_connection, news_source_id=test_news_source.id
        )

        # Then
        assert result == []
        assert len(result) == 0

        # Verify last_scraped_at was still updated
        updated_source = await db_connection.fetchrow(
            "SELECT * FROM news_sources WHERE id = $1", test_news_source.id
        )
        assert updated_source["last_scraped_at"] is not None
