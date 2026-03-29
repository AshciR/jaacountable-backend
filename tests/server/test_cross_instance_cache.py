"""Tests proving that two app instances sharing a RedisCacheBackend serve
cached responses from each other's warm cache, while two InMemoryCache
instances do NOT share state across process boundaries."""

import asyncpg
from unittest.mock import AsyncMock

from src.article_persistence.models.domain import Article
from src.article_persistence.repositories.article_repository import ArticleRepository
from src.cache.in_memory import InMemoryCache
from src.server.articles.schemas import ArticleSearchParams
from src.server.articles.service import ArticleSearchService


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _insert_article(
    conn: asyncpg.Connection,
    *,
    url: str,
    title: str,
    full_text: str,
) -> Article:
    repo = ArticleRepository()
    return await repo.insert_article(
        conn,
        Article(
            url=url,
            title=title,
            section="news",
            full_text=full_text,
            news_source_id=1,
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCrossInstanceCacheSharing:
    """Redis cache is shared across service instances; InMemoryCache is not."""

    async def test_instance_b_hits_redis_cache_populated_by_instance_a(
        self,
        redis_cache,
        db_connection: asyncpg.Connection,
    ):
        # Given: one article in the DB
        await _insert_article(
            db_connection,
            url="https://gleaner.com/indecom-budget",
            title="INDECOM budget cut",
            full_text="The Independent Commission of Investigations faces a major budget cut.",
        )
        params = ArticleSearchParams(q="indecom")

        # Instance A — real repo + shared Redis cache (cache miss → populates Redis)
        service_a = ArticleSearchService(cache=redis_cache)
        results_a, total_a = await service_a.search(db_connection, params)

        # Instance B — mock repo + same Redis cache (should hit cache, never touch DB)
        mock_repo = AsyncMock(spec=ArticleRepository)
        service_b = ArticleSearchService(repo=mock_repo, cache=redis_cache)
        results_b, total_b = await service_b.search(db_connection, params)

        # Then: B served results from Redis without querying the database
        mock_repo.search_articles.assert_not_called()
        assert total_b == total_a
        assert [r.url for r in results_b] == [r.url for r in results_a]

    async def test_in_memory_cache_does_not_share_across_instances(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: one article in the DB
        await _insert_article(
            db_connection,
            url="https://gleaner.com/indecom-budget-inmem",
            title="INDECOM budget cut (in-memory)",
            full_text="The Independent Commission of Investigations faces a major budget cut.",
        )
        params = ArticleSearchParams(q="indecom")

        # Instance A — warms its own InMemoryCache
        cache_a = InMemoryCache()
        service_a = ArticleSearchService(cache=cache_a)
        await service_a.search(db_connection, params)

        # Instance B — separate InMemoryCache; cache_a's data is invisible to it
        cache_b = InMemoryCache()
        mock_repo = AsyncMock(spec=ArticleRepository)
        mock_repo.search_articles = AsyncMock(return_value=([], 0))
        service_b = ArticleSearchService(repo=mock_repo, cache=cache_b)
        await service_b.search(db_connection, params)

        # Then: B got a cache miss and had to query its own repo
        mock_repo.search_articles.assert_called_once()
