"""Database configuration and connection pool management."""
import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import urlparse, urlunparse
import asyncpg
from loguru import logger


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
    ) -> asyncpg.Pool:
        """
        Create and return a connection pool.

        Args:
            min_size: Minimum number of connections in the pool
            max_size: Maximum number of connections in the pool
            command_timeout: Timeout for commands in seconds

        Returns:
            asyncpg.Pool: Connection pool instance
        """
        async with self._pool_lock:
            if self._pool is None:
                self._pool = await asyncpg.create_pool(
                    self.get_asyncpg_url(),
                    min_size=min_size,
                    max_size=max_size,
                    command_timeout=command_timeout,
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


# Global database configuration instance
db_config = DatabaseConfig()
