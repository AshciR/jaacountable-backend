"""
Pytest configuration and fixtures for database testing.

This module provides fixtures for testing database operations using testcontainers
to spin up an isolated PostgreSQL instance for each test session.
"""

import logging
import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from alembic import command
from alembic.config import Config
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

import boto3
from botocore.config import Config as BotocoreConfig
from testcontainers.localstack import LocalStackContainer

from config.database import DatabaseConfig
from src.cache.redis_cache import RedisCacheBackend

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """
    Start a PostgreSQL container for the test session.

    This fixture is session-scoped, meaning the container is started once
    and shared across all tests in the session.
    """
    # Use same credentials as .env.example for consistency
    postgres = PostgresContainer(
        image="postgres:17-alpine",
        username="user",
        password="password",
        dbname="jaacountable_db",
    )

    with postgres:
        # Log connection details for debugging
        host = postgres.get_container_host_ip()
        port = postgres.get_exposed_port(5432)
        logger.info("=" * 60)
        logger.info("Test PostgreSQL Container Started")
        logger.info("=" * 60)
        logger.info(f"  Host: {host}")
        logger.info(f"  Port: {port}")
        logger.info(f"  Database: jaacountable_db")
        logger.info(f"  Username: user")
        logger.info(f"  Password: password")
        logger.info(f"  URL: {postgres.get_connection_url()}")
        logger.info("=" * 60)

        yield postgres


@pytest.fixture(scope="session")
def test_database_url(postgres_container: PostgresContainer) -> str:
    """
    Get the database URL from the PostgreSQL container.

    Returns the connection URL in the format expected by asyncpg.
    """
    return postgres_container.get_connection_url()


@pytest.fixture(scope="session")
def run_migrations(test_database_url: str) -> None:
    """
    Run Alembic migrations on the test database.

    This fixture runs all migrations to set up the database schema
    before any tests run.
    """
    # Get the project root directory (parent of tests/)
    project_root = Path(__file__).parent.parent
    alembic_ini_path = project_root / "alembic.ini"

    # Create Alembic config
    alembic_cfg = Config(str(alembic_ini_path))

    # Convert psycopg2 URL format to SQLAlchemy async format
    # testcontainers returns: postgresql+psycopg2://user:pass@host:port/article_persistence
    # We need: postgresql+asyncpg://user:pass@host:port/article_persistence
    sqlalchemy_url = test_database_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    # Set DATABASE_URL env var so alembic/env.py picks it up
    # (env.py reads from environment and overrides config)
    os.environ["DATABASE_URL"] = sqlalchemy_url

    # Set the database URL in the config
    alembic_cfg.set_main_option("sqlalchemy.url", sqlalchemy_url)

    # Run migrations to head
    command.upgrade(alembic_cfg, "head")


@pytest_asyncio.fixture(scope="session")
async def db_pool(
    test_database_url: str, run_migrations: None
) -> AsyncGenerator[asyncpg.Pool, None]:
    """
    Create an asyncpg connection pool for the test database.

    This fixture depends on run_migrations to ensure the schema is set up
    before creating the pool.
    """
    # Convert testcontainers URL to asyncpg format expected by DatabaseConfig
    # testcontainers returns: postgresql+psycopg2://user:pass@host:port/article_persistence
    # DatabaseConfig expects: postgresql+asyncpg://user:pass@host:port/article_persistence
    database_url = test_database_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    # Use DatabaseConfig with test URL
    db_config = DatabaseConfig(database_url=database_url)
    pool = await db_config.create_pool(min_size=2, max_size=10)

    try:
        yield pool
    finally:
        await db_config.close_pool()


@pytest.fixture(scope="session")
def redis_container() -> Generator[RedisContainer, None, None]:
    """
    Start a Redis container for the test session.

    Session-scoped so the container starts once and is shared across all tests.
    """
    with RedisContainer("redis:8-alpine") as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        logger.info("=" * 60)
        logger.info("Test Redis Container Started")
        logger.info("=" * 60)
        logger.info(f"  Host: {host}")
        logger.info(f"  Port: {port}")
        logger.info("=" * 60)
        yield container


@pytest_asyncio.fixture
async def redis_client(
    redis_container: RedisContainer,
) -> AsyncGenerator[aioredis.Redis, None]:
    """
    Provide an async Redis client with automatic cleanup after each test.

    Calls FLUSHDB in teardown to mirror the transaction-rollback isolation
    pattern used by db_connection.
    """
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    client = aioredis.from_url(f"redis://{host}:{port}")
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest_asyncio.fixture
async def redis_cache(redis_client: aioredis.Redis) -> RedisCacheBackend:
    """Provide a RedisCacheBackend wired to the test Redis container."""
    return RedisCacheBackend(client=redis_client)


@pytest_asyncio.fixture
async def db_connection(
    db_pool: asyncpg.Pool,
) -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Provide a database connection with automatic transaction rollback.

    Each test gets a fresh connection with a transaction that is rolled back
    after the test completes, ensuring test isolation.
    """
    async with db_pool.acquire() as connection:
        # Start a transaction
        transaction = connection.transaction()
        await transaction.start()

        try:
            yield connection
        finally:
            # Roll back the transaction to ensure test isolation
            await transaction.rollback()


@pytest.fixture(scope="session")
def localstack_container() -> Generator[LocalStackContainer, None, None]:
    """Start a LocalStack container for the test session."""
    with LocalStackContainer() as container:
        yield container


@pytest.fixture(scope="session")
def s3_client(localstack_container: LocalStackContainer):
    """Factory fixture that returns a boto3 S3 client and creates the named bucket.

    Usage in tests:
        def test_something(s3_client):
            client = s3_client("my-test-bucket")
    """
    _created_buckets: set[str] = set()

    def _make_client(bucket_name: str):
        client = boto3.client(
            "s3",
            endpoint_url=localstack_container.get_url(),
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name="us-east-1",
            config=BotocoreConfig(s3={"addressing_style": "path"}),
        )
        if bucket_name not in _created_buckets:
            client.create_bucket(Bucket=bucket_name)
            _created_buckets.add(bucket_name)
        return client

    return _make_client
