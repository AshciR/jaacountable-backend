"""Database configuration and connection pool management."""
import asyncio
import os
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Optional, TypeVar
from urllib.parse import urlparse, urlunparse
import asyncpg
from loguru import logger

_POOL_CONNECT_TIMEOUT = float(os.getenv("DB_POOL_CONNECT_TIMEOUT", "10.0"))
_POOL_MAX_RETRIES = int(os.getenv("DB_POOL_MAX_RETRIES", "5"))
_POOL_RETRY_BASE_BACKOFF = float(os.getenv("DB_POOL_RETRY_BASE_BACKOFF", "2.0"))

T = TypeVar("T")


class DatabaseConfig:
    """Database configuration and connection pool manager."""

    def __init__(self, database_url: str | None = None):
        self.database_url: str = database_url or os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://user:password@localhost:5432/jaacountable_db"
        )
        self._pool: Optional[asyncpg.Pool] = None
        self._pool_lock = asyncio.Lock()

    async def __aenter__(self):
        """Allow using DatabaseConfig as an async context manager."""
        await self.create_pool()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ensure pool is closed when exiting context."""
        await self.close_pool()

    @asynccontextmanager
    async def connection(self):
        """
        Get a connection as an async context manager.
        Automatically releases the connection when done.

        Usage:
            async with db_config.connection() as conn:
                result = await conn.fetch("SELECT * FROM users")

        Yields:
            asyncpg.Connection: Database connection from the pool

        Raises:
            RuntimeError: If connection pool is not initialized
        """
        conn = await self.get_connection()
        try:
            yield conn
        finally:
            await self.release_connection(conn)

    @staticmethod
    def mask_url(url: str) -> str:
        """Return a database URL with credentials partially masked for logging.

        Replaces username and password with ****{last4chars} to confirm
        which credential set is in use without exposing secrets.
        """
        parsed = urlparse(url)
        username = parsed.username or ""
        password = parsed.password or ""
        masked_user = f"****{username[-4:]}" if username else ""
        masked_pass = f"****{password[-4:]}" if password else ""
        if masked_user or masked_pass:
            userinfo = f"{masked_user}:{masked_pass}" if masked_pass else masked_user
            host = parsed.hostname or ""
            if parsed.port:
                host = f"{host}:{parsed.port}"
            netloc = f"{userinfo}@{host}"
        else:
            netloc = parsed.netloc
        return urlunparse(parsed._replace(netloc=netloc))

    def get_asyncpg_url(self) -> str:
        """
        Convert DATABASE_URL to asyncpg format if needed.
        Removes '+asyncpg' suffix if present since asyncpg.create_pool expects 'postgresql://'.
        """
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql+asyncpg://", "postgresql://")
        return url

    async def create_pool(
        self,
        min_size: int = int(os.getenv("DB_POOL_MIN_SIZE", "1")),
        max_size: int = int(os.getenv("DB_POOL_MAX_SIZE", "5")),
        command_timeout: float = 60.0,
        connect_timeout: float = _POOL_CONNECT_TIMEOUT,
        max_retries: int = _POOL_MAX_RETRIES,
        base_backoff: float = _POOL_RETRY_BASE_BACKOFF,
    ) -> asyncpg.Pool:
        """
        Create and return a connection pool.

        Retries with exponential backoff on connection failures (e.g. app container
        network not yet ready after cold start / hibernation wake-up).

        Args:
            min_size: Minimum number of connections in the pool
            max_size: Maximum number of connections in the pool
            command_timeout: Timeout for individual queries in seconds
            connect_timeout: Timeout for establishing each connection attempt in seconds
            max_retries: Maximum number of connection attempts before giving up
            base_backoff: Base for exponential backoff between attempts (base^attempt seconds)

        Returns:
            asyncpg.Pool: Connection pool instance
        """
        async with self._pool_lock:
            if self._pool is None:
                attempt_count = 0

                # retry_with_backoff requires a function as an argument
                # we create the pool inside a function to accomplish this.
                async def _create() -> asyncpg.Pool:
                    nonlocal attempt_count
                    attempt_count += 1
                    return await asyncpg.create_pool(
                        self.get_asyncpg_url(),
                        min_size=min_size,
                        max_size=max_size,
                        command_timeout=command_timeout,
                        timeout=connect_timeout,
                    )

                # Startup Failure: asyncpg Pool Timeout due to Cancelled Connection
                # What's wrong: Application startup fails due to asyncpg connection pool creation timeout.
                # Fix: Add retry logic while attempts to connect to the database
                # Context: https://github.com/AshciR/jaacountable-backend/issues/188
                self._pool = await retry_with_backoff(
                    _create,
                    retry_on=(OSError, asyncpg.PostgresConnectionError),
                    max_retries=max_retries,
                    base_backoff=base_backoff,
                    label="Database pool creation",
                )

                attempt_note = f" (after {attempt_count} attempts)" if attempt_count > 1 else ""
                logger.info(
                    "Database pool created{}: url={}, min_size={}, max_size={}",
                    attempt_note,
                    self.mask_url(self.get_asyncpg_url()),
                    min_size,
                    max_size,
                )
            return self._pool

    async def close_pool(self) -> None:
        """Close the connection pool if it exists."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def get_connection(self) -> asyncpg.Connection:
        """
        Get a connection from the pool.

        Returns:
            asyncpg.Connection: Database connection

        Raises:
            RuntimeError: If pool hasn't been created yet
        """
        if self._pool is None:
            raise RuntimeError(
                "Connection pool not initialized. Call create_pool() first."
            )
        return await self._pool.acquire()

    async def release_connection(self, conn: asyncpg.Connection) -> None:
        """
        Release a connection back to the pool.

        Args:
            conn: Connection to release
        """
        if self._pool is not None:
            await self._pool.release(conn)

    def get_pool_stats(self) -> dict[str, int]:
        """
        Get current connection pool statistics.

        Returns:
            dict with pool statistics:
                - size: Current number of connections in pool
                - idle: Number of idle (free) connections
                - acquired: Number of currently acquired connections
                - min_size: Minimum pool size
                - max_size: Maximum pool size

        Raises:
            RuntimeError: If pool hasn't been created yet
        """
        if self._pool is None:
            raise RuntimeError(
                "Connection pool not initialized. Call create_pool() first."
            )

        return {
            "size": self._pool.get_size(),
            "idle": self._pool.get_idle_size(),
            "acquired": self._pool.get_size() - self._pool.get_idle_size(),
            "min_size": self._pool.get_min_size(),
            "max_size": self._pool.get_max_size(),
        }


async def retry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    *,
    retry_on: tuple[type[Exception], ...],
    max_retries: int,
    base_backoff: float,
    label: str = "operation",
) -> T:
    """
    Execute an async callable with exponential backoff retries.

    Args:
        fn: Async callable to execute (no arguments; use a lambda or partial to bind args).
        retry_on: Tuple of exception types that should trigger a retry.
        max_retries: Maximum number of attempts before re-raising.
        base_backoff: Base for exponential delay — attempt N waits base^N seconds.
        label: Human-readable name shown in log messages.

    Returns:
        The return value of fn on success.

    Raises:
        The last exception raised by fn if all attempts fail.
    """
    for attempt in range(1, max_retries + 1):
        try:
            return await fn()
        except retry_on as e:
            if attempt < max_retries:
                backoff_time = base_backoff ** attempt
                logger.warning(
                    "{} failed (attempt {}/{}) : {}. Retrying in {:.1f}s...",
                    label,
                    attempt,
                    max_retries,
                    e,
                    backoff_time,
                )
                await asyncio.sleep(backoff_time)
            else:
                logger.error(
                    "{} failed after {} attempts. Giving up.",
                    label,
                    max_retries,
                )
                raise

# Global database configuration instance
db_config = DatabaseConfig()
