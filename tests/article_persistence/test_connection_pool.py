"""Tests for connection pool health and leak detection."""

import asyncio
import uuid

import asyncpg
import pytest

from src.article_persistence.repositories.article_repository import ArticleRepository
from src.article_persistence.models.domain import Article


def get_pool_stats(pool: asyncpg.Pool) -> dict[str, int]:
    """Get pool statistics."""
    return {
        'size': pool.get_size(),
        'idle': pool.get_idle_size(),
        'acquired': pool.get_size() - pool.get_idle_size(),
        'min_size': pool.get_min_size(),
        'max_size': pool.get_max_size(),
    }


class TestPoolConnectionRelease:
    """Tests for proper connection release back to pool."""

    async def test_single_operation_releases_connection(
        self,
        db_pool: asyncpg.Pool,
    ):
        # Given: a connection pool with known initial state
        stats_before = get_pool_stats(db_pool)
        repository = ArticleRepository()
        unique_id = uuid.uuid4().hex

        # When: a single insert operation is performed within a connection context
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                article = Article(
                    url=f"https://test.com/single-op-{unique_id}",
                    title="Single Operation Test",
                    section="test",
                    news_source_id=1,
                )
                await repository.insert_article(conn, article)

                # During operation: connection should be acquired
                stats_during = get_pool_stats(db_pool)
                assert stats_during['acquired'] >= 1

        # Then: connection is released back to pool
        stats_after = get_pool_stats(db_pool)
        assert stats_after['acquired'] == stats_before['acquired']

    async def test_multiple_sequential_operations_no_accumulation(
        self,
        db_pool: asyncpg.Pool,
    ):
        # Given: a connection pool with known initial state
        stats_before = get_pool_stats(db_pool)
        repository = ArticleRepository()

        # When: multiple sequential insert operations are performed
        for i in range(5):
            unique_id = uuid.uuid4().hex
            async with db_pool.acquire() as conn:
                async with conn.transaction():
                    article = Article(
                        url=f"https://test.com/sequential-{i}-{unique_id}",
                        title=f"Sequential Test {i}",
                        section="test",
                        news_source_id=1,
                    )
                    await repository.insert_article(conn, article)

        # Then: all connections are released, no accumulation
        stats_after = get_pool_stats(db_pool)
        assert stats_after['acquired'] == stats_before['acquired']

    async def test_connection_released_on_exception(
        self,
        db_pool: asyncpg.Pool,
    ):
        # Given: a connection pool with known initial state and an existing article
        stats_before = get_pool_stats(db_pool)
        repository = ArticleRepository()
        duplicate_url = f"https://test.com/duplicate-{uuid.uuid4().hex}"

        # Insert first article
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                first_article = Article(
                    url=duplicate_url,
                    title="First Insert",
                    section="test",
                    news_source_id=1,
                )
                await repository.insert_article(conn, first_article)

        # When: an operation fails with UniqueViolationError
        with pytest.raises(asyncpg.UniqueViolationError):
            async with db_pool.acquire() as conn:
                async with conn.transaction():
                    duplicate_article = Article(
                        url=duplicate_url,
                        title="Duplicate Insert",
                        section="test",
                        news_source_id=1,
                    )
                    await repository.insert_article(conn, duplicate_article)

        # Then: connection is still released despite exception
        stats_after = get_pool_stats(db_pool)
        assert stats_after['acquired'] == stats_before['acquired']


class TestPoolConcurrentOperations:
    """Tests for concurrent connection management."""

    async def test_concurrent_operations_release_all_connections(
        self,
        db_pool: asyncpg.Pool,
    ):
        # Given: a connection pool with known initial state
        stats_before = get_pool_stats(db_pool)
        repository = ArticleRepository()

        # When: multiple concurrent insert operations are performed
        async def insert_task(task_id: int):
            unique_id = uuid.uuid4().hex
            async with db_pool.acquire() as conn:
                async with conn.transaction():
                    article = Article(
                        url=f"https://test.com/concurrent-{task_id}-{unique_id}",
                        title=f"Concurrent Article {task_id}",
                        section="test",
                        news_source_id=1,
                    )
                    await repository.insert_article(conn, article)
                    # Small delay to ensure overlap
                    await asyncio.sleep(0.01)

        tasks = [insert_task(i) for i in range(10)]
        await asyncio.gather(*tasks)

        # Then: all connections are released back to pool
        stats_after = get_pool_stats(db_pool)
        assert stats_after['acquired'] == stats_before['acquired']

    async def test_pool_handles_burst_of_requests(
        self,
        db_pool: asyncpg.Pool,
    ):
        # Given: a connection pool with known max size
        stats_before = get_pool_stats(db_pool)
        repository = ArticleRepository()
        max_pool_size = stats_before['max_size']

        # When: a burst of requests equal to max pool size is made
        async def insert_task(task_id: int):
            unique_id = uuid.uuid4().hex
            async with db_pool.acquire() as conn:
                async with conn.transaction():
                    article = Article(
                        url=f"https://test.com/burst-{task_id}-{unique_id}",
                        title=f"Burst Article {task_id}",
                        section="test",
                        news_source_id=1,
                    )
                    await repository.insert_article(conn, article)

        tasks = [insert_task(i) for i in range(max_pool_size)]
        await asyncio.gather(*tasks)

        # Then: pool handled all requests and released connections
        stats_after = get_pool_stats(db_pool)
        assert stats_after['acquired'] == stats_before['acquired']
        # Pool size should not exceed max
        assert stats_after['size'] <= max_pool_size
