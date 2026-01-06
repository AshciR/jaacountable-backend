"""In-memory cache implementation for entity normalization with TTL + LRU eviction."""
import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass

from loguru import logger

from src.article_classification.models import NormalizedEntity


@dataclass
class CacheEntry:
    """Cache entry with TTL tracking."""
    entity: NormalizedEntity
    timestamp: float  # Unix timestamp when entry was created


class InMemoryEntityCache:
    """
    In-memory LRU cache for normalized entities with TTL support.

    Features:
    - Cache key normalization (lowercase + whitespace collapse)
    - TTL-based expiration (default 14 days)
    - LRU eviction (default 100k max entries)
    - Hit rate metrics

    Thread Safety: Uses asyncio.Lock for async context
    Concurrency: Designed for single-process asyncio deployment
    """

    def __init__(
        self,
        max_size: int = 100_000,
        ttl_seconds: int = 14 * 24 * 60 * 60  # 14 days
    ):
        """
        Initialize cache with LRU eviction and TTL.

        Args:
            max_size: Maximum cache entries before LRU eviction (default 100k)
            ttl_seconds: Time-to-live in seconds (default 14 days)
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

        # Metrics
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
            "total_sets": 0,
        }

        logger.info(
            f"Initialized InMemoryEntityCache "
            f"(max_size={max_size:,}, ttl={ttl_seconds:,}s)"
        )

    async def get(self, entity_name: str) -> NormalizedEntity | None:
        """Retrieve entity from cache with key normalization and TTL check."""
        cache_key = self._normalize_key(entity_name)

        async with self._lock:
            entry = self._cache.get(cache_key)

            if entry is None:
                self._stats["misses"] += 1
                logger.debug(f"Cache MISS: '{entity_name}' (key='{cache_key}')")
                return None

            # Check TTL
            if self._is_expired(entry):
                del self._cache[cache_key]
                self._stats["expirations"] += 1
                self._stats["misses"] += 1
                logger.debug(
                    f"Cache EXPIRED: '{entity_name}' "
                    f"(age={(time.time() - entry.timestamp):.0f}s)"
                )
                return None

            # LRU: Move to end (most recently used)
            self._cache.move_to_end(cache_key)
            self._stats["hits"] += 1
            logger.debug(
                f"Cache HIT: '{entity_name}' → '{entry.entity.normalized_value}'"
            )
            return entry.entity

    async def set(self, entity_name: str, normalized: NormalizedEntity) -> None:
        """Store entity in cache with TTL and LRU eviction."""
        cache_key = self._normalize_key(entity_name)

        async with self._lock:
            # Remove if already exists (to update timestamp and position)
            if cache_key in self._cache:
                del self._cache[cache_key]

            # LRU eviction if at capacity
            if len(self._cache) >= self._max_size:
                evicted_key, _ = self._cache.popitem(last=False)  # Remove oldest
                self._stats["evictions"] += 1
                logger.warning(
                    f"LRU EVICTION: cache full at {self._max_size:,} entries "
                    f"(evicted '{evicted_key}')"
                )

            # Store with timestamp
            self._cache[cache_key] = CacheEntry(
                entity=normalized,
                timestamp=time.time()
            )
            self._stats["total_sets"] += 1
            logger.debug(f"Cache SET: '{entity_name}' → '{normalized.normalized_value}'")

    async def get_many(self, entity_names: list[str]) -> dict[str, NormalizedEntity]:
        """
        Retrieve multiple entities (batch operation) with TTL checks.

        Reuses get() for each entity to maintain single responsibility and
        ensure consistent TTL/LRU behavior.
        """
        results: dict[str, NormalizedEntity] = {}

        for entity_name in entity_names:
            entity = await self.get(entity_name)
            if entity is not None:
                results[entity_name] = entity

        logger.debug(
            f"Cache get_many: {len(results)} hits, "
            f"{len(entity_names) - len(results)} misses"
        )

        return results

    async def set_many(self, normalizations: dict[str, NormalizedEntity]) -> None:
        """
        Store multiple entities (batch operation) with TTL.

        Reuses set() for each entity to maintain single responsibility and
        ensure consistent TTL/LRU/eviction behavior.
        """
        for entity_name, normalized in normalizations.items():
            await self.set(entity_name, normalized)

        logger.debug(f"Cache set_many: stored {len(normalizations)} entities")

    def get_stats(self) -> dict:
        """Get cache statistics including hit rate."""
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total_requests if total_requests > 0 else 0.0

        return {
            **self._stats,
            "size": len(self._cache),
            "max_size": self._max_size,
            "hit_rate": hit_rate,
            "ttl_seconds": self._ttl_seconds,
        }

    def size(self) -> int:
        """Get current cache size (for testing/debugging)."""
        return len(self._cache)

    async def clear(self) -> None:
        """Clear cache (for testing)."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats = {
                "hits": 0,
                "misses": 0,
                "evictions": 0,
                "expirations": 0,
                "total_sets": 0,
            }
            logger.info(f"Cache cleared: removed {count} entities")

    def _normalize_key(self, entity_name: str) -> str:
        """
        Normalize cache key: lowercase + collapse whitespace.

        Examples:
            "Hon. Ruel Reid  " → "hon. ruel reid"
            "OCG" → "ocg"
            "PM   Holness" → "pm holness"
        """
        return " ".join(entity_name.lower().split())

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if cache entry has exceeded TTL."""
        return (time.time() - entry.timestamp) > self._ttl_seconds


# Module-level singleton instance
_cache_instance: InMemoryEntityCache | None = None


def get_entity_cache(
    max_size: int = 100_000,
    ttl_seconds: int = 14 * 24 * 60 * 60
) -> InMemoryEntityCache:
    """
    Get or create module-level singleton cache instance.

    This ensures all EntityNormalizerService instances share the same cache
    in a single-process asyncio deployment.

    Args:
        max_size: Maximum cache entries (only used on first call)
        ttl_seconds: Time-to-live in seconds (only used on first call)

    Returns:
        Singleton InMemoryEntityCache instance
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = InMemoryEntityCache(
            max_size=max_size,
            ttl_seconds=ttl_seconds
        )
        logger.info("Created singleton entity cache instance")
    return _cache_instance
