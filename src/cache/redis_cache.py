"""Redis cache backend."""
import redis.asyncio as aioredis
from loguru import logger


class RedisCacheBackend:
    """
    Cache backend backed by Redis (or a Redis-compatible store such as Valkey).

    Accepts an injected ``redis.asyncio.Redis`` client so the caller controls
    connection pooling and lifecycle (connect on startup, close on shutdown).
    """

    def __init__(self, client: aioredis.Redis, ttl_seconds: int = 300) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    async def get(self, key: str) -> str | None:
        """Return cached value for key, or None if missing/expired."""
        value = await self._client.get(key)
        if value is None:
            logger.debug("cache miss key={}", key)
            return None
        logger.debug("cache hit key={}", key)
        return value.decode() if isinstance(value, bytes) else value

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store value under key with a TTL in seconds."""
        await self._client.set(key, value, ex=ttl_seconds)
        logger.debug("cache set key={} ttl={}s", key, ttl_seconds)

    async def delete(self, key: str) -> None:
        """Remove a key from the cache."""
        await self._client.delete(key)
        logger.debug("cache delete key={}", key)

    def size(self) -> int:
        """Not meaningful for a distributed cache; returns -1."""
        return -1

    async def close(self) -> None:
        """Close the underlying Redis connection."""
        await self._client.aclose()
