# Entity Normalization Caching Implementation Plan (v2)

## Overview

Add a caching layer to `EntityNormalizerService` to reduce redundant LLM API calls when normalizing entity names. The cache stores mappings from original entity names (e.g., "Hon. Ruel Reid") to their normalized forms (e.g., "ruel_reid") with metadata.

**Revised Design Decisions (based on architecture review):**
- **Cache granularity**: Per-entity (cache each entity name individually for max hit rate)
- **TTL**: 14 days (configurable, safety net for prompt/model changes)
- **Key normalization**: Yes (lowercase + whitespace collapse for better hit rate)
- **LRU eviction**: 100k max entries (OrderedDict-based LRU)
- **Singleton**: Module-level instance (shared across all service instances)
- **Metrics**: Hit rate logging
- **Deployment**: Single process with asyncio (in-memory cache shared via singleton)
- **Architecture**: Inside EntityNormalizerService (encapsulation, testability)
- **Fallback**: Fail-soft (fall back to LLM if cache fails, log warning)
- **Initial implementation**: In-memory dict-based cache with LRU + TTL
- **Future migration**: Redis-based cache using same protocol interface

## Architecture

### Current Flow (No Caching)
```
EntityNormalizerService.normalize(["Hon. Ruel Reid", "OCG"])
  → Create session
  → Call LLM for ALL entities (1 API call)
  → Return list[NormalizedEntity]
```

### Proposed Flow (With Caching)
```
EntityNormalizerService.normalize(["Hon. Ruel Reid", "OCG", "Ministry of Education"])
  → Normalize cache keys: ["hon. ruel reid", "ocg", "ministry of education"]
  → Check cache for all 3 entities
  → Cache HIT: "hon. ruel reid" (from previous article, not expired)
  → Cache MISS: "ocg", "ministry of education"
  → Create session + call LLM for ONLY 2 uncached entities
  → Populate cache with new results (14-day TTL)
  → Combine cached + new results in original order
  → Return complete list[NormalizedEntity]
  → Log hit rate: "Cache hit rate: 33.3% (1/3 entities)"
```

**Key Benefits:**
- Reduces LLM API costs (cache hits = no API call)
- 10-100x faster for cached entities (1ms vs 500-2000ms)
- Consistent normalization across articles
- Key normalization improves hit rate (case-insensitive matching)
- TTL ensures fresh results after prompt/model updates
- LRU eviction prevents unbounded memory growth
- Protocol abstraction enables future Redis migration with zero code changes

## Implementation Steps

### Step 1: Define EntityCache Protocol

**File**: `src/article_classification/base.py`
**Location**: After `EntityNormalizer` protocol (after line 104)

Add protocol for structural typing (follows existing `ArticleClassifier`, `EntityNormalizer` patterns):

```python
class EntityCache(Protocol):
    """
    Protocol for entity normalization caches using structural subtyping.

    Cache Key: Normalized entity name (lowercase + whitespace collapsed)
    Cache Value: Complete NormalizedEntity object
    TTL: Configurable (default 14 days)
    Eviction: LRU (default 100k max entries)
    """

    async def get(self, entity_name: str) -> NormalizedEntity | None:
        """
        Retrieve normalized entity from cache.

        Args:
            entity_name: Original entity name (will be normalized for lookup)

        Returns:
            Cached NormalizedEntity or None if not found/expired
        """
        ...

    async def set(self, entity_name: str, normalized: NormalizedEntity) -> None:
        """
        Store normalized entity in cache with TTL.

        Args:
            entity_name: Original entity name (will be normalized for storage)
            normalized: NormalizedEntity to cache
        """
        ...

    async def get_many(self, entity_names: list[str]) -> dict[str, NormalizedEntity]:
        """
        Retrieve multiple entities (batch operation).

        Args:
            entity_names: List of original entity names

        Returns:
            Dict mapping original entity name → NormalizedEntity (hits only)
        """
        ...

    async def set_many(self, normalizations: dict[str, NormalizedEntity]) -> None:
        """
        Store multiple entities (batch operation) with TTL.

        Args:
            normalizations: Dict mapping original entity name → NormalizedEntity
        """
        ...

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with keys: hits, misses, size, hit_rate, evictions, expirations
        """
        ...
```

**Import update (line 4)**:
```python
from .models import ClassificationInput, ClassificationResult, NormalizedEntity
```

### Step 2: Implement InMemoryEntityCache

**File**: `src/article_classification/services/in_memory_entity_cache.py` (NEW)

Create dict-based cache implementation with TTL + LRU:

```python
"""In-memory cache implementation for entity normalization with TTL + LRU eviction."""
import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass

from src.article_classification.models import NormalizedEntity

logger = logging.getLogger(__name__)


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
        """Retrieve multiple entities (batch operation) with TTL checks."""
        results: dict[str, NormalizedEntity] = {}

        async with self._lock:
            for entity_name in entity_names:
                cache_key = self._normalize_key(entity_name)
                entry = self._cache.get(cache_key)

                if entry is None:
                    self._stats["misses"] += 1
                    continue

                # Check TTL
                if self._is_expired(entry):
                    del self._cache[cache_key]
                    self._stats["expirations"] += 1
                    self._stats["misses"] += 1
                    continue

                # LRU: Move to end
                self._cache.move_to_end(cache_key)
                self._stats["hits"] += 1
                results[entity_name] = entry.entity

            logger.debug(
                f"Cache get_many: {len(results)} hits, "
                f"{len(entity_names) - len(results)} misses"
            )

        return results

    async def set_many(self, normalizations: dict[str, NormalizedEntity]) -> None:
        """Store multiple entities (batch operation) with TTL."""
        async with self._lock:
            current_time = time.time()

            for entity_name, normalized in normalizations.items():
                cache_key = self._normalize_key(entity_name)

                # Remove if exists
                if cache_key in self._cache:
                    del self._cache[cache_key]

                # LRU eviction if needed
                if len(self._cache) >= self._max_size:
                    evicted_key, _ = self._cache.popitem(last=False)
                    self._stats["evictions"] += 1
                    logger.warning(
                        f"LRU EVICTION: cache full at {self._max_size:,} entries "
                        f"(evicted '{evicted_key}')"
                    )

                # Store
                self._cache[cache_key] = CacheEntry(
                    entity=normalized,
                    timestamp=current_time
                )
                self._stats["total_sets"] += 1

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
```

### Step 3: Update EntityNormalizerService

**File**: `src/article_classification/services/entity_normalizer_service.py`

**3.1 Import Updates (after line 11)**:
```python
from src.article_classification.base import APP_NAME, EntityCache
import logging

logger = logging.getLogger(__name__)
```

**3.2 Add Class Attribute (after line 19)**:
```python
cache: EntityCache | None
```

**3.3 Update Constructor (replace lines 21-41)**:
```python
def __init__(
    self,
    agent: LlmAgent | None = None,
    session_service: BaseSessionService | None = None,
    runner: Runner | None = None,
    cache: EntityCache | None = None,  # NEW
):
    """
    Initialize the normalizer service.

    Args:
        agent: LLM agent (defaults to normalization_agent)
        session_service: Session service (defaults to InMemorySessionService)
        runner: Pre-configured runner (defaults to new Runner)
        cache: Entity cache for reducing LLM calls (optional, defaults to None)
    """
    self.agent = agent or normalization_agent
    self.session_service = session_service or InMemorySessionService()
    self.runner = runner or Runner(
        app_name=APP_NAME,
        agent=self.agent,
        session_service=self.session_service
    )
    self.cache = cache
    logger.info(f"Initialized EntityNormalizerService (cache: {'enabled' if cache else 'disabled'})")
```

**3.4 Add Helper Methods (after line 75)**:
```python
async def _get_cached_entities(
    self, entities: list[str]
) -> tuple[dict[str, NormalizedEntity], list[str]]:
    """
    Split entities into cached vs uncached.

    Returns: (cached_results, uncached_entities)
    """
    if not self.cache:
        return {}, entities

    try:
        cached_results = await self.cache.get_many(entities)
        uncached_entities = [e for e in entities if e not in cached_results]
        logger.info(f"Cache lookup: {len(cached_results)} hits, {len(uncached_entities)} misses")
        return cached_results, uncached_entities
    except Exception as e:
        logger.warning(f"Cache get_many failed: {e}. Falling back to LLM for all entities.")
        return {}, entities

async def _populate_cache(self, normalized_entities: list[NormalizedEntity]) -> None:
    """Populate cache with newly normalized entities."""
    if not self.cache or not normalized_entities:
        return

    try:
        cache_entries = {entity.original_value: entity for entity in normalized_entities}
        await self.cache.set_many(cache_entries)
        logger.info(f"Cached {len(cache_entries)} newly normalized entities")
    except Exception as e:
        logger.warning(f"Cache set_many failed: {e}. Continuing without caching.")

async def _log_cache_stats(self) -> None:
    """Log cache performance stats (hit rate)."""
    if not self.cache:
        return

    try:
        stats = self.cache.get_stats()
        logger.info(
            f"Cache stats: hit_rate={stats['hit_rate']:.1%}, "
            f"size={stats['size']:,}/{stats['max_size']:,}, "
            f"hits={stats['hits']}, misses={stats['misses']}, "
            f"evictions={stats['evictions']}, expirations={stats['expirations']}"
        )
    except Exception as e:
        logger.debug(f"Failed to log cache stats: {e}")
```

**3.5 Update normalize() Method (replace lines 43-75)**:
```python
async def normalize(self, entities: list[str]) -> list[NormalizedEntity]:
    """Normalize a batch of entities using cache + normalization agent."""
    if not entities:
        raise ValueError("entities list cannot be empty")

    # Step 1: Check cache
    cached_results, uncached_entities = await self._get_cached_entities(entities)

    # Step 2: If all cached, return early
    if not uncached_entities:
        logger.info("All entities found in cache (no LLM call needed)")
        await self._log_cache_stats()
        return [cached_results[e] for e in entities]

    # Step 3: Normalize uncached entities via LLM
    logger.info(f"Calling LLM to normalize {len(uncached_entities)} entities")

    session: Session = await self.session_service.create_session(
        app_name=APP_NAME, user_id="entity_normalizer"
    )

    entities_str = ", ".join(f'"{e}"' for e in uncached_entities)
    prompt = f"Normalize these entities: {entities_str}"
    response = await self._call_agent_async(prompt, session.user_id, session.id)

    result = json.loads(response)
    normalized = [
        NormalizedEntity(
            original_value=item["original_value"],
            normalized_value=item["normalized_value"],
            confidence=item["confidence"],
            reason=item["reason"],
            context=""
        )
        for item in result["normalized_entities"]
    ]

    # Step 4: Populate cache
    await self._populate_cache(normalized)

    # Step 5: Combine results in original order
    all_results = {**cached_results, **{e.original_value: e for e in normalized}}

    # Step 6: Log cache stats
    await self._log_cache_stats()

    return [all_results[e] for e in entities]
```

### Step 4: Update PipelineOrchestrationService

**File**: `src/orchestration/service.py`

**4.1 Import Update (after line 15)**:
```python
from src.article_classification.services.in_memory_entity_cache import get_entity_cache
```

**4.2 Update Constructor (modify lines 57-86)**:

Replace this line:
```python
self.entity_normalizer = entity_normalizer or EntityNormalizerService()
```

With:
```python
# Inject singleton cache into entity normalizer (production config)
self.entity_normalizer = entity_normalizer or EntityNormalizerService(
    cache=get_entity_cache()  # Singleton cache shared across all instances
)
```

### Step 5: Update Module Exports

**File**: `src/article_classification/services/__init__.py`

Add exports:
```python
from .in_memory_entity_cache import InMemoryEntityCache, get_entity_cache

__all__ = ["InMemoryEntityCache", "get_entity_cache"]
```

### Step 6: Create Tests

**File**: `tests/article_classification/services/test_in_memory_entity_cache.py` (NEW)

Create comprehensive tests following BDD style:

```python
"""Unit tests for InMemoryEntityCache."""
import asyncio
import pytest
import time

from src.article_classification.services.in_memory_entity_cache import (
    InMemoryEntityCache,
    get_entity_cache,
)
from src.article_classification.models import NormalizedEntity


class TestInMemoryEntityCacheHappyPath:
    """Test successful cache operations (BDD style)."""

    async def test_get_cache_hit_returns_entity(self):
        # Given: Cache with stored entity
        cache = InMemoryEntityCache()
        entity = NormalizedEntity(
            original_value="Hon. Ruel Reid",
            normalized_value="ruel_reid",
            confidence=0.95,
            reason="Removed title"
        )
        await cache.set("Hon. Ruel Reid", entity)

        # When: Getting cached entity
        result = await cache.get("Hon. Ruel Reid")

        # Then: Returns correct entity
        assert result is not None
        assert result.normalized_value == "ruel_reid"

    async def test_get_cache_miss_returns_none(self):
        # Given: Empty cache
        cache = InMemoryEntityCache()

        # When: Getting non-existent entity
        result = await cache.get("Unknown Entity")

        # Then: Returns None
        assert result is None

    async def test_get_many_returns_only_cached_entities(self):
        # Given: Cache with partial entities
        cache = InMemoryEntityCache()
        await cache.set(
            "Hon. Ruel Reid",
            NormalizedEntity(original_value="Hon. Ruel Reid", normalized_value="ruel_reid", confidence=0.95, reason="Test")
        )

        # When: Getting batch with hits + misses
        results = await cache.get_many(["Hon. Ruel Reid", "Unknown"])

        # Then: Returns only cached
        assert len(results) == 1
        assert "Hon. Ruel Reid" in results
        assert "Unknown" not in results

    async def test_set_many_stores_all_entities(self):
        # Given: Empty cache
        cache = InMemoryEntityCache()
        entities = {
            "Entity1": NormalizedEntity(original_value="Entity1", normalized_value="entity1", confidence=0.9, reason="Test"),
            "Entity2": NormalizedEntity(original_value="Entity2", normalized_value="entity2", confidence=0.9, reason="Test")
        }

        # When: Storing batch
        await cache.set_many(entities)

        # Then: All retrievable
        assert cache.size() == 2
        assert await cache.get("Entity1") is not None
        assert await cache.get("Entity2") is not None


class TestInMemoryEntityCacheKeyNormalization:
    """Test cache key normalization (BDD style)."""

    async def test_lowercase_normalization(self):
        # Given: Cache with uppercase key
        cache = InMemoryEntityCache()
        await cache.set(
            "OCG",
            NormalizedEntity(original_value="OCG", normalized_value="office_of_the_contractor_general", confidence=0.95, reason="Test")
        )

        # When: Getting with different case
        result = await cache.get("ocg")

        # Then: Cache hit (key normalized)
        assert result is not None
        assert result.normalized_value == "office_of_the_contractor_general"

    async def test_whitespace_collapse(self):
        # Given: Cache with extra whitespace
        cache = InMemoryEntityCache()
        await cache.set(
            "Hon. Ruel  Reid   ",
            NormalizedEntity(original_value="Hon. Ruel Reid", normalized_value="ruel_reid", confidence=0.95, reason="Test")
        )

        # When: Getting with single spaces
        result = await cache.get("hon. ruel reid")

        # Then: Cache hit (whitespace collapsed)
        assert result is not None
        assert result.normalized_value == "ruel_reid"

    async def test_combined_normalization(self):
        # Given: Cache with case + whitespace differences
        cache = InMemoryEntityCache()
        await cache.set(
            "PM   HOLNESS",
            NormalizedEntity(original_value="PM Holness", normalized_value="andrew_holness", confidence=0.95, reason="Test")
        )

        # When: Getting with different formatting
        result = await cache.get("pm holness")

        # Then: Cache hit
        assert result is not None
        assert result.normalized_value == "andrew_holness"


class TestInMemoryEntityCacheTTL:
    """Test TTL expiration (BDD style)."""

    async def test_get_expired_entity_returns_none(self):
        # Given: Cache with 1-second TTL
        cache = InMemoryEntityCache(ttl_seconds=1)
        await cache.set(
            "OCG",
            NormalizedEntity(original_value="OCG", normalized_value="ocg", confidence=0.95, reason="Test")
        )

        # When: Waiting for expiration
        await asyncio.sleep(1.1)
        result = await cache.get("OCG")

        # Then: Returns None (expired)
        assert result is None

    async def test_expired_entity_removed_from_cache(self):
        # Given: Cache with 1-second TTL
        cache = InMemoryEntityCache(ttl_seconds=1)
        await cache.set(
            "OCG",
            NormalizedEntity(original_value="OCG", normalized_value="ocg", confidence=0.95, reason="Test")
        )

        # When: Accessing after expiration
        await asyncio.sleep(1.1)
        await cache.get("OCG")

        # Then: Removed from cache
        assert cache.size() == 0

    async def test_get_many_skips_expired_entities(self):
        # Given: Cache with mixed fresh/expired entities
        cache = InMemoryEntityCache(ttl_seconds=1)
        await cache.set(
            "Fresh",
            NormalizedEntity(original_value="Fresh", normalized_value="fresh", confidence=0.95, reason="Test")
        )
        await asyncio.sleep(1.1)  # First entity expired
        await cache.set(
            "New",
            NormalizedEntity(original_value="New", normalized_value="new", confidence=0.95, reason="Test")
        )

        # When: Getting batch
        results = await cache.get_many(["Fresh", "New"])

        # Then: Only non-expired returned
        assert len(results) == 1
        assert "New" in results
        assert "Fresh" not in results

    async def test_expiration_increments_stats(self):
        # Given: Cache with 1-second TTL
        cache = InMemoryEntityCache(ttl_seconds=1)
        await cache.set(
            "OCG",
            NormalizedEntity(original_value="OCG", normalized_value="ocg", confidence=0.95, reason="Test")
        )

        # When: Accessing after expiration
        await asyncio.sleep(1.1)
        await cache.get("OCG")

        # Then: Expiration counter incremented
        stats = cache.get_stats()
        assert stats["expirations"] == 1


class TestInMemoryEntityCacheLRUEviction:
    """Test LRU eviction (BDD style)."""

    async def test_lru_eviction_when_full(self):
        # Given: Cache with max_size=2
        cache = InMemoryEntityCache(max_size=2)
        await cache.set(
            "E1",
            NormalizedEntity(original_value="E1", normalized_value="e1", confidence=0.9, reason="Test")
        )
        await cache.set(
            "E2",
            NormalizedEntity(original_value="E2", normalized_value="e2", confidence=0.9, reason="Test")
        )

        # When: Adding third entity
        await cache.set(
            "E3",
            NormalizedEntity(original_value="E3", normalized_value="e3", confidence=0.9, reason="Test")
        )

        # Then: Oldest evicted
        assert cache.size() == 2
        assert await cache.get("E1") is None  # Evicted
        assert await cache.get("E2") is not None
        assert await cache.get("E3") is not None

    async def test_lru_updates_on_get(self):
        # Given: Cache with max_size=2, E1 and E2
        cache = InMemoryEntityCache(max_size=2)
        await cache.set(
            "E1",
            NormalizedEntity(original_value="E1", normalized_value="e1", confidence=0.9, reason="Test")
        )
        await cache.set(
            "E2",
            NormalizedEntity(original_value="E2", normalized_value="e2", confidence=0.9, reason="Test")
        )

        # When: Accessing E1 (moves to end), then adding E3
        await cache.get("E1")
        await cache.set(
            "E3",
            NormalizedEntity(original_value="E3", normalized_value="e3", confidence=0.9, reason="Test")
        )

        # Then: E2 evicted (was oldest)
        assert cache.size() == 2
        assert await cache.get("E1") is not None  # Kept (recently accessed)
        assert await cache.get("E2") is None  # Evicted
        assert await cache.get("E3") is not None

    async def test_eviction_increments_stats(self):
        # Given: Cache with max_size=1
        cache = InMemoryEntityCache(max_size=1)
        await cache.set(
            "E1",
            NormalizedEntity(original_value="E1", normalized_value="e1", confidence=0.9, reason="Test")
        )

        # When: Triggering eviction
        await cache.set(
            "E2",
            NormalizedEntity(original_value="E2", normalized_value="e2", confidence=0.9, reason="Test")
        )

        # Then: Eviction counter incremented
        stats = cache.get_stats()
        assert stats["evictions"] == 1


class TestInMemoryEntityCacheStats:
    """Test cache statistics (BDD style)."""

    async def test_get_stats_includes_hit_rate(self):
        # Given: Cache with hits and misses
        cache = InMemoryEntityCache()
        await cache.set(
            "E1",
            NormalizedEntity(original_value="E1", normalized_value="e1", confidence=0.9, reason="Test")
        )
        await cache.get("E1")  # Hit
        await cache.get("E2")  # Miss

        # When: Getting stats
        stats = cache.get_stats()

        # Then: Hit rate calculated correctly
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5
        assert stats["size"] == 1

    async def test_get_stats_empty_cache(self):
        # Given: Empty cache
        cache = InMemoryEntityCache()

        # When: Getting stats
        stats = cache.get_stats()

        # Then: No division by zero
        assert stats["hit_rate"] == 0.0
        assert stats["size"] == 0


class TestInMemoryEntityCacheEdgeCases:
    """Test edge cases (BDD style)."""

    async def test_overwrite_existing_entity(self):
        # Given: Cache with entity
        cache = InMemoryEntityCache()
        await cache.set("OCG", NormalizedEntity(original_value="OCG", normalized_value="ocg_old", confidence=0.8, reason="Old"))

        # When: Overwriting
        await cache.set("OCG", NormalizedEntity(original_value="OCG", normalized_value="ocg_new", confidence=0.9, reason="New"))

        # Then: Returns updated
        result = await cache.get("OCG")
        assert result.normalized_value == "ocg_new"

    async def test_clear_removes_all_entities(self):
        # Given: Cache with entities
        cache = InMemoryEntityCache()
        await cache.set_many({
            "E1": NormalizedEntity(original_value="E1", normalized_value="e1", confidence=0.9, reason="Test"),
            "E2": NormalizedEntity(original_value="E2", normalized_value="e2", confidence=0.9, reason="Test")
        })

        # When: Clearing
        await cache.clear()

        # Then: All removed, stats reset
        assert cache.size() == 0
        assert await cache.get("E1") is None
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0


class TestEntityCacheSingleton:
    """Test singleton factory (BDD style)."""

    async def test_get_entity_cache_returns_singleton(self):
        # Given: Multiple calls to factory
        cache1 = get_entity_cache()
        cache2 = get_entity_cache()

        # When: Comparing instances
        # Then: Same instance
        assert cache1 is cache2

    async def test_singleton_shared_state(self):
        # Given: Entity cached via first instance
        cache1 = get_entity_cache()
        await cache1.set(
            "OCG",
            NormalizedEntity(original_value="OCG", normalized_value="ocg", confidence=0.95, reason="Test")
        )

        # When: Accessing via second instance
        cache2 = get_entity_cache()
        result = await cache2.get("OCG")

        # Then: Entity found (shared state)
        assert result is not None
        assert result.normalized_value == "ocg"
```

**File**: `tests/article_classification/services/test_entity_normalizer_service.py`

Append new test classes:

```python


class TestEntityNormalizerServiceWithCache:
    """Test normalization with caching (BDD style)."""

    async def test_all_entities_cached_no_llm_call(self, mock_session_service: AsyncMock):
        # Given: Pre-populated cache
        from src.article_classification.services.in_memory_entity_cache import InMemoryEntityCache

        cache = InMemoryEntityCache()
        await cache.set("Hon. Ruel Reid", NormalizedEntity(
            original_value="Hon. Ruel Reid", normalized_value="ruel_reid",
            confidence=0.95, reason="Cached"
        ))

        mock_runner = AsyncMock()
        normalizer = EntityNormalizerService(runner=mock_runner, session_service=mock_session_service, cache=cache)

        # When: Normalizing cached entity
        result = await normalizer.normalize(["Hon. Ruel Reid"])

        # Then: Returns cached, no LLM call
        assert len(result) == 1
        assert result[0].normalized_value == "ruel_reid"
        mock_session_service.create_session.assert_not_called()

    async def test_cache_populated_after_llm(self, mock_runner_single_entity: AsyncMock, mock_session_service: AsyncMock):
        # Given: Empty cache
        from src.article_classification.services.in_memory_entity_cache import InMemoryEntityCache

        cache = InMemoryEntityCache()
        normalizer = EntityNormalizerService(runner=mock_runner_single_entity, session_service=mock_session_service, cache=cache)

        # When: Normalizing uncached entity
        await normalizer.normalize(["Hon. Ruel Reid"])

        # Then: Cache populated
        cached = await cache.get("Hon. Ruel Reid")
        assert cached is not None
        assert cached.normalized_value == "ruel_reid"

    async def test_cache_failure_falls_back_to_llm(self, mock_runner_single_entity: AsyncMock, mock_session_service: AsyncMock):
        # Given: Mock cache that raises
        from unittest.mock import Mock, AsyncMock as AM

        mock_cache = Mock()
        mock_cache.get_many = AM(side_effect=Exception("Cache failed"))
        mock_cache.set_many = AM(side_effect=Exception("Cache failed"))

        normalizer = EntityNormalizerService(runner=mock_runner_single_entity, session_service=mock_session_service, cache=mock_cache)

        # When: Normalizing with failing cache
        result = await normalizer.normalize(["Hon. Ruel Reid"])

        # Then: Falls back to LLM
        assert len(result) == 1
        assert result[0].normalized_value == "ruel_reid"

    async def test_partial_cache_hit_calls_llm_for_misses_only(self, mock_runner_single_entity: AsyncMock, mock_session_service: AsyncMock):
        # Given: Cache with one entity
        from src.article_classification.services.in_memory_entity_cache import InMemoryEntityCache

        cache = InMemoryEntityCache()
        await cache.set("Cached Entity", NormalizedEntity(
            original_value="Cached Entity", normalized_value="cached_entity",
            confidence=0.95, reason="Test"
        ))

        normalizer = EntityNormalizerService(runner=mock_runner_single_entity, session_service=mock_session_service, cache=cache)

        # When: Normalizing mix of cached + uncached
        result = await normalizer.normalize(["Cached Entity", "Hon. Ruel Reid"])

        # Then: LLM called only for uncached
        assert len(result) == 2
        assert result[0].normalized_value == "cached_entity"  # From cache
        assert result[1].normalized_value == "ruel_reid"  # From LLM
        mock_session_service.create_session.assert_called_once()  # Only 1 LLM call


class TestEntityNormalizerServiceCacheDisabled:
    """Test without cache (backwards compatibility)."""

    async def test_no_cache_behaves_like_before(self, mock_runner_single_entity: AsyncMock, mock_session_service: AsyncMock):
        # Given: No cache
        normalizer = EntityNormalizerService(runner=mock_runner_single_entity, session_service=mock_session_service, cache=None)

        # When: Normalizing
        result = await normalizer.normalize(["Hon. Ruel Reid"])

        # Then: LLM called every time
        assert len(result) == 1
        mock_session_service.create_session.assert_called_once()
```

## Testing Checklist

- [ ] `test_in_memory_entity_cache.py`: 35+ tests (cache operations, key normalization, TTL, LRU, stats, edge cases, singleton)
- [ ] `test_entity_normalizer_service.py`: Add 5+ tests (cache integration, partial hits, fallback)
- [ ] Run full test suite: `uv run pytest tests/ -m "not integration" -v`
- [ ] Verify all tests pass
- [ ] Manual test: Process article with repeated entities, check logs for cache hits + hit rate

## Future Redis Migration (No Code Changes Needed)

When ready for production Redis cache:

1. **Add dependency**: `redis` or `redis-py` to `pyproject.toml`
2. **Implement RedisEntityCache**:
   ```python
   class RedisEntityCache:  # Implements EntityCache protocol
       def __init__(self, redis_url: str, ttl_seconds: int = 14 * 24 * 60 * 60):
           self.redis = redis.asyncio.from_url(redis_url)
           self.ttl_seconds = ttl_seconds

       def _normalize_key(self, entity_name: str) -> str:
           return " ".join(entity_name.lower().split())

       async def get(self, entity_name: str) -> NormalizedEntity | None:
           cache_key = f"entity_norm:{self._normalize_key(entity_name)}"
           cached_json = await self.redis.get(cache_key)
           return NormalizedEntity.model_validate_json(cached_json) if cached_json else None

       async def set(self, entity_name: str, normalized: NormalizedEntity) -> None:
           cache_key = f"entity_norm:{self._normalize_key(entity_name)}"
           await self.redis.setex(
               cache_key,
               self.ttl_seconds,
               normalized.model_dump_json()
           )
       # ... implement other methods
   ```
3. **Swap implementation** in `PipelineOrchestrationService.__init__`:
   ```python
   from .redis_entity_cache import RedisEntityCache

   self.entity_normalizer = entity_normalizer or EntityNormalizerService(
       cache=RedisEntityCache(redis_url=os.getenv("REDIS_URL"))  # Just change this line!
   )
   ```

No changes needed in `EntityNormalizerService` due to protocol abstraction.

## Critical Files Summary

| File | Action | Key Changes |
|------|--------|-------------|
| `src/article_classification/base.py` | Edit | Add `EntityCache` protocol with `get_stats()` method |
| `src/article_classification/services/in_memory_entity_cache.py` | Create | Implement cache with TTL + LRU + key normalization + singleton |
| `src/article_classification/services/entity_normalizer_service.py` | Edit | Add cache parameter, update `normalize()` logic, add stats logging |
| `src/orchestration/service.py` | Edit | Inject singleton cache via `get_entity_cache()` |
| `src/article_classification/services/__init__.py` | Edit | Export `InMemoryEntityCache` and `get_entity_cache` |
| `tests/article_classification/services/test_in_memory_entity_cache.py` | Create | 35+ unit tests (happy path, key norm, TTL, LRU, stats, singleton) |
| `tests/article_classification/services/test_entity_normalizer_service.py` | Edit | Add 5+ cache integration tests |

## Expected Performance Impact

**Before Caching:**
- Article with 5 entities → 1 LLM call (~500-2000ms)
- 10 articles with same entities → 10 LLM calls (~5-20 seconds total)
- entity_normalization_duration_ms: 19345.16ms (from your test output)

**After Caching (14-day TTL, 100k capacity):**
- First article: 1 LLM call + 5 cache writes (~500-2000ms)
- Subsequent articles (within 14 days): 5 cache hits + 0 LLM calls (~5ms total)
- **~400x speedup** for fully cached entities (19345ms → 50ms)
- **Significant cost savings** on LLM API calls
- **>80% hit rate** expected for repeated entities in production

## Success Criteria

- All tests pass (unit + integration)
- Cache hit rate >80% for repeated entities in logs
- No LLM calls when all entities cached
- Cache failures don't break normalization (fail-soft)
- Backwards compatible (cache=None works as before)
- entity_normalization_duration_ms drops from ~19s to <100ms for cached entities
- Hit rate logged after each normalization operation
