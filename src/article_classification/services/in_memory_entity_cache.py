"""In-memory entity cache backed by CacheBackend (swappable for Redis)."""
from loguru import logger

from src.article_classification.models import NormalizedEntity
from src.cache.cache_interface import CacheBackend
from src.cache.in_memory import InMemoryCache


class InMemoryEntityCache:
    """
    Entity cache implementing the EntityCache protocol.

    Delegates storage to a CacheBackend (InMemoryCache by default, Redis-swappable).
    Handles entity-specific concerns: key normalization and NormalizedEntity serialization.

    Thread Safety: Delegated to the underlying CacheBackend
    Concurrency: Designed for single-process asyncio deployment
    """

    def __init__(
        self,
        cache: CacheBackend,
        max_size: int = 100_000,
        ttl_seconds: int = 14 * 24 * 60 * 60,  # 14 days
    ):
        self._cache = cache
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._hits = 0
        self._misses = 0
        logger.info(
            f"Initialized InMemoryEntityCache "
            f"(max_size={max_size:,}, ttl={ttl_seconds:,}s)"
        )

    async def get(self, entity_name: str) -> NormalizedEntity | None:
        """Retrieve entity from cache with key normalization."""
        cache_key = self._normalize_key(entity_name)
        value = await self._cache.get(cache_key)

        if value is None:
            self._misses += 1
            logger.debug(f"Cache MISS: '{entity_name}' (key='{cache_key}')")
            return None

        self._hits += 1
        entity = NormalizedEntity.model_validate_json(value)
        logger.debug(f"Cache HIT: '{entity_name}' → '{entity.normalized_value}'")
        return entity

    async def set(self, entity_name: str, normalized: NormalizedEntity) -> None:
        """Store entity in cache."""
        cache_key = self._normalize_key(entity_name)
        await self._cache.set(cache_key, normalized.model_dump_json(), self._ttl_seconds)
        logger.debug(f"Cache SET: '{entity_name}' → '{normalized.normalized_value}'")

    async def get_many(self, entity_names: list[str]) -> dict[str, NormalizedEntity]:
        """Retrieve multiple entities (batch operation)."""
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
        """Store multiple entities (batch operation)."""
        for entity_name, normalized in normalizations.items():
            await self.set(entity_name, normalized)

        logger.debug(f"Cache set_many: stored {len(normalizations)} entities")

    def get_stats(self) -> dict:
        """Get cache statistics including hit rate."""
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": self._cache.size(),
            "max_size": self._max_size,
            "hit_rate": hit_rate,
            "ttl_seconds": self._ttl_seconds,
        }

    def size(self) -> int:
        """Get current cache size."""
        return self._cache.size()

    def _normalize_key(self, entity_name: str) -> str:
        """
        Normalize cache key: lowercase + collapse whitespace.

        Examples:
            "Hon. Ruel Reid  " → "hon. ruel reid"
            "OCG" → "ocg"
            "PM   Holness" → "pm holness"
        """
        return " ".join(entity_name.lower().split())


# Module-level singleton instance
_cache_instance: InMemoryEntityCache | None = None


def get_entity_cache(
    max_size: int = 100_000,
    ttl_seconds: int = 14 * 24 * 60 * 60,
) -> InMemoryEntityCache:
    """
    Get or create module-level singleton entity cache instance.

    Backed by InMemoryCache. To swap to Redis: replace InMemoryCache(...)
    with a Redis CacheBackend implementation here.

    Args:
        max_size: Maximum cache entries (only used on first call)
        ttl_seconds: Time-to-live in seconds (only used on first call)

    Returns:
        Singleton InMemoryEntityCache instance
    """
    global _cache_instance
    if _cache_instance is None:
        backing = InMemoryCache(max_size=max_size, ttl_seconds=ttl_seconds)
        _cache_instance = InMemoryEntityCache(
            cache=backing,
            max_size=max_size,
            ttl_seconds=ttl_seconds,
        )
        logger.info("Created singleton entity cache instance")
    return _cache_instance
