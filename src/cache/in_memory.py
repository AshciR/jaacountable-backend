"""In-memory cache implementation with TTL + LRU eviction."""
import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass

from loguru import logger


@dataclass
class _CacheEntry:
    value: str
    timestamp: float  # Unix timestamp when entry was created
    ttl_seconds: int


class InMemoryCache:
    """
    In-memory LRU cache storing string values with per-entry TTL support.

    Features:
    - TTL-based expiration (checked on read)
    - LRU eviction when max_size is reached
    - Thread-safe via asyncio.Lock

    Concurrency: Designed for single-process asyncio deployment.
    To swap for Redis: implement CacheBackend protocol with an async Redis client.
    """

    def __init__(self, max_size: int = 1_000, ttl_seconds: int = 300):
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        """Return cached value, or None if missing or expired."""
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                logger.debug(f"Cache MISS: '{key}'")
                return None

            if (time.time() - entry.timestamp) > entry.ttl_seconds:
                del self._cache[key]
                logger.debug(f"Cache EXPIRED: '{key}'")
                return None

            self._cache.move_to_end(key)
            logger.debug(f"Cache HIT: '{key}'")
            return entry.value

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store value under key with the given TTL."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]

            if len(self._cache) >= self._max_size:
                evicted_key, _ = self._cache.popitem(last=False)
                logger.warning(
                    f"Cache LRU eviction: '{evicted_key}' "
                    f"(max_size={self._max_size:,})"
                )

            self._cache[key] = _CacheEntry(
                value=value,
                timestamp=time.time(),
                ttl_seconds=ttl_seconds,
            )
            logger.debug(f"Cache SET: '{key}' (ttl={ttl_seconds}s)")

    async def delete(self, key: str) -> None:
        """Remove a key from the cache."""
        async with self._lock:
            self._cache.pop(key, None)
            logger.debug(f"Cache DELETE: '{key}'")

    def size(self) -> int:
        """Current number of entries (includes potentially expired entries)."""
        return len(self._cache)
