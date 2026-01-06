"""Unit tests for InMemoryEntityCache."""
import asyncio
import pytest

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

    async def test_key_normalization_deduplicates_variants(self):
        # Given: Cache with one entity
        cache = InMemoryEntityCache()
        await cache.set(
            "OCG",
            NormalizedEntity(original_value="OCG", normalized_value="ocg_v1", confidence=0.95, reason="Test")
        )

        # When: Setting same entity with different formatting
        await cache.set(
            "  ocg  ",
            NormalizedEntity(original_value="ocg", normalized_value="ocg_v2", confidence=0.95, reason="Test")
        )

        # Then: Only one entry exists (overwritten)
        assert cache.size() == 1
        result = await cache.get("OCG")
        assert result.normalized_value == "ocg_v2"  # Latest wins


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

    async def test_fresh_entity_not_expired(self):
        # Given: Cache with 10-second TTL
        cache = InMemoryEntityCache(ttl_seconds=10)
        await cache.set(
            "OCG",
            NormalizedEntity(original_value="OCG", normalized_value="ocg", confidence=0.95, reason="Test")
        )

        # When: Getting immediately
        result = await cache.get("OCG")

        # Then: Still cached
        assert result is not None
        assert result.normalized_value == "ocg"


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

    async def test_set_many_respects_lru_limit(self):
        # Given: Cache with max_size=2
        cache = InMemoryEntityCache(max_size=2)
        await cache.set(
            "E1",
            NormalizedEntity(original_value="E1", normalized_value="e1", confidence=0.9, reason="Test")
        )

        # When: Adding 2 more entities via set_many
        await cache.set_many({
            "E2": NormalizedEntity(original_value="E2", normalized_value="e2", confidence=0.9, reason="Test"),
            "E3": NormalizedEntity(original_value="E3", normalized_value="e3", confidence=0.9, reason="Test"),
        })

        # Then: Oldest evicted, size maintained
        assert cache.size() == 2
        assert await cache.get("E1") is None  # Evicted
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

    async def test_get_stats_includes_all_metrics(self):
        # Given: Cache with various operations
        cache = InMemoryEntityCache(max_size=1, ttl_seconds=1)
        await cache.set(
            "E1",
            NormalizedEntity(original_value="E1", normalized_value="e1", confidence=0.9, reason="Test")
        )
        await cache.get("E1")  # Hit
        await cache.set(
            "E2",
            NormalizedEntity(original_value="E2", normalized_value="e2", confidence=0.9, reason="Test")
        )  # Eviction
        await asyncio.sleep(1.1)
        await cache.get("E2")  # Expiration

        # When: Getting stats
        stats = cache.get_stats()

        # Then: All metrics present
        assert "hits" in stats
        assert "misses" in stats
        assert "evictions" in stats
        assert "expirations" in stats
        assert "total_sets" in stats
        assert "size" in stats
        assert "max_size" in stats
        assert "hit_rate" in stats
        assert "ttl_seconds" in stats

    async def test_get_many_updates_hit_miss_stats(self):
        # Given: Cache with one entity
        cache = InMemoryEntityCache()
        await cache.set(
            "E1",
            NormalizedEntity(original_value="E1", normalized_value="e1", confidence=0.9, reason="Test")
        )

        # When: Getting batch with hits and misses
        await cache.get_many(["E1", "E2", "E3"])

        # Then: Stats updated correctly
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 2


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
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0

        # And: Previously cached entities no longer found
        assert await cache.get("E1") is None
        assert await cache.get("E2") is None

    async def test_get_many_with_empty_list(self):
        # Given: Cache with entities
        cache = InMemoryEntityCache()
        await cache.set(
            "E1",
            NormalizedEntity(original_value="E1", normalized_value="e1", confidence=0.9, reason="Test")
        )

        # When: Getting with empty list
        results = await cache.get_many([])

        # Then: Returns empty dict
        assert results == {}

    async def test_set_many_with_empty_dict(self):
        # Given: Cache
        cache = InMemoryEntityCache()

        # When: Setting with empty dict
        await cache.set_many({})

        # Then: No error, cache empty
        assert cache.size() == 0


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

    async def test_singleton_parameters_ignored_after_first_call(self):
        # Given: First call with default params
        cache1 = get_entity_cache()
        original_max_size = cache1._max_size

        # When: Second call with different params
        cache2 = get_entity_cache(max_size=50_000, ttl_seconds=7 * 24 * 60 * 60)

        # Then: Same instance, original params preserved
        assert cache1 is cache2
        assert cache2._max_size == original_max_size  # Not 50_000
