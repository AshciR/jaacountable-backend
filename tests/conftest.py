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
from alembic import command
from alembic.config import Config
from testcontainers.postgres import PostgresContainer

from config.database import DatabaseConfig

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
        image="postgres:18-alpine",
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
