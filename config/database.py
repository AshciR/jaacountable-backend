"""Database configuration and connection pool management."""
import asyncio
import os
from typing import Optional
import asyncpg


class DatabaseConfig:
    """Database configuration and connection pool manager."""

    def __init__(self):
        self.database_url: str = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://user:password@localhost:5432/jaacountable_db"
        )
        self._pool: Optional[asyncpg.Pool] = None
        self._pool_lock = asyncio.Lock()

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
        min_size: int = 10,
        max_size: int = 20,
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

    async def __aenter__(self):
        """Allow using DatabaseConfig as an async context manager."""
        await self.create_pool()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ensure pool is closed when exiting context."""
        await self.close_pool()


# Global database configuration instance
db_config = DatabaseConfig()
