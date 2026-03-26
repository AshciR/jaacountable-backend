"""Unit tests for InMemoryEntityCache (adapter over CacheBackend)."""
import asyncio
import pytest

import src.article_classification.services.in_memory_entity_cache as cache_module
from src.article_classification.services.in_memory_entity_cache import (
    InMemoryEntityCache,
    get_entity_cache,
)
from src.article_classification.models import NormalizedEntity
from src.cache.in_memory import InMemoryCache


def make_cache(max_size: int = 100, ttl_seconds: int = 300) -> InMemoryEntityCache:
    """Create a test cache backed by a real InMemoryCache."""
    backing = InMemoryCache(max_size=max_size, ttl_seconds=ttl_seconds)
    return InMemoryEntityCache(cache=backing, max_size=max_size, ttl_seconds=ttl_seconds)


def make_entity(original: str, normalized: str, confidence: float = 0.9) -> NormalizedEntity:
    return NormalizedEntity(
        original_value=original,
        normalized_value=normalized,
        confidence=confidence,
        reason="Test",
    )


class TestInMemoryEntityCacheHappyPath:
    """Test successful cache operations (BDD style)."""

    async def test_get_cache_hit_returns_entity(self):
        # Given: Cache with stored entity
        cache = make_cache()
        entity = make_entity("Hon. Ruel Reid", "ruel_reid", confidence=0.95)
        await cache.set("Hon. Ruel Reid", entity)

        # When: Getting cached entity
        result = await cache.get("Hon. Ruel Reid")

        # Then: Returns correct entity
        assert result is not None
        assert result.normalized_value == "ruel_reid"

    async def test_get_cache_miss_returns_none(self):
        # Given: Empty cache
        cache = make_cache()

        # When: Getting non-existent entity
        result = await cache.get("Unknown Entity")

        # Then: Returns None
        assert result is None

    async def test_serialization_preserves_all_fields(self):
        # Given: Entity with all fields populated
        cache = make_cache()
        entity = NormalizedEntity(
            original_value="Hon. Ruel Reid",
            normalized_value="ruel_reid",
            confidence=0.95,
            reason="Removed title",
            context="Jamaica education minister",
        )
        await cache.set("Hon. Ruel Reid", entity)

        # When: Retrieving
        result = await cache.get("Hon. Ruel Reid")

        # Then: All fields round-trip correctly
        assert result is not None
        assert result.original_value == "Hon. Ruel Reid"
        assert result.normalized_value == "ruel_reid"
        assert result.confidence == 0.95
        assert result.reason == "Removed title"
        assert result.context == "Jamaica education minister"

    async def test_get_many_returns_only_cached_entities(self):
        # Given: Cache with partial entities
        cache = make_cache()
        await cache.set("Hon. Ruel Reid", make_entity("Hon. Ruel Reid", "ruel_reid"))

        # When: Getting batch with hits + misses
        results = await cache.get_many(["Hon. Ruel Reid", "Unknown"])

        # Then: Returns only cached
        assert len(results) == 1
        assert "Hon. Ruel Reid" in results
        assert "Unknown" not in results

    async def test_set_many_stores_all_entities(self):
        # Given: Empty cache
        cache = make_cache()
        entities = {
            "Entity1": make_entity("Entity1", "entity1"),
            "Entity2": make_entity("Entity2", "entity2"),
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
        cache = make_cache()
        await cache.set("OCG", make_entity("OCG", "office_of_the_contractor_general"))

        # When: Getting with lowercase
        result = await cache.get("ocg")

        # Then: Cache hit (key normalized)
        assert result is not None
        assert result.normalized_value == "office_of_the_contractor_general"

    async def test_whitespace_collapse(self):
        # Given: Cache with extra whitespace in key
        cache = make_cache()
        await cache.set("Hon. Ruel  Reid   ", make_entity("Hon. Ruel Reid", "ruel_reid"))

        # When: Getting with single spaces
        result = await cache.get("hon. ruel reid")

        # Then: Cache hit (whitespace collapsed)
        assert result is not None
        assert result.normalized_value == "ruel_reid"

    async def test_combined_normalization(self):
        # Given: Cache with mixed case + extra whitespace
        cache = make_cache()
        await cache.set("PM   HOLNESS", make_entity("PM Holness", "andrew_holness"))

        # When: Getting with normalized form
        result = await cache.get("pm holness")

        # Then: Cache hit
        assert result is not None
        assert result.normalized_value == "andrew_holness"

    async def test_key_normalization_deduplicates_variants(self):
        # Given: Cache with one entity
        cache = make_cache()
        await cache.set("OCG", make_entity("OCG", "ocg_v1"))

        # When: Setting same entity with different formatting (overwrite)
        await cache.set("  ocg  ", make_entity("ocg", "ocg_v2"))

        # Then: Only one entry (overwritten), latest value wins
        assert cache.size() == 1
        result = await cache.get("OCG")
        assert result.normalized_value == "ocg_v2"


class TestInMemoryEntityCacheTTL:
    """Test that TTL is correctly forwarded to the backing store (BDD style)."""

    async def test_entity_accessible_within_ttl(self):
        # Given: Cache with generous TTL
        cache = make_cache(ttl_seconds=60)
        await cache.set("OCG", make_entity("OCG", "ocg"))

        # When: Getting immediately
        result = await cache.get("OCG")

        # Then: Still accessible
        assert result is not None

    async def test_expired_entity_returns_none(self):
        # Given: Cache with 1-second TTL
        cache = make_cache(ttl_seconds=1)
        await cache.set("OCG", make_entity("OCG", "ocg"))

        # When: Waiting for expiration
        await asyncio.sleep(1.1)
        result = await cache.get("OCG")

        # Then: Returns None (expired in backing store)
        assert result is None


class TestInMemoryEntityCacheStats:
    """Test hit/miss statistics (BDD style)."""

    async def test_get_stats_hit_rate(self):
        # Given: Cache with one hit and one miss
        cache = make_cache()
        await cache.set("E1", make_entity("E1", "e1"))
        await cache.get("E1")   # Hit
        await cache.get("E2")   # Miss

        # When: Getting stats
        stats = cache.get_stats()

        # Then: Correct hit rate
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5
        assert stats["size"] == 1

    async def test_get_stats_empty_cache_no_division_by_zero(self):
        # Given: Empty cache with no requests
        cache = make_cache()

        # When: Getting stats
        stats = cache.get_stats()

        # Then: Zero hit rate, no error
        assert stats["hit_rate"] == 0.0
        assert stats["size"] == 0

    async def test_get_stats_includes_required_keys(self):
        # Given: Cache with activity
        cache = make_cache(max_size=10, ttl_seconds=60)
        await cache.set("E1", make_entity("E1", "e1"))
        await cache.get("E1")

        # When: Getting stats
        stats = cache.get_stats()

        # Then: All expected keys present
        assert "hits" in stats
        assert "misses" in stats
        assert "size" in stats
        assert "max_size" in stats
        assert "hit_rate" in stats
        assert "ttl_seconds" in stats

    async def test_get_many_updates_hit_miss_stats(self):
        # Given: Cache with one entity
        cache = make_cache()
        await cache.set("E1", make_entity("E1", "e1"))

        # When: Batch get with one hit, two misses
        await cache.get_many(["E1", "E2", "E3"])

        # Then: Stats reflect individual get() calls
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 2


class TestInMemoryEntityCacheEdgeCases:
    """Test edge cases (BDD style)."""

    async def test_overwrite_existing_entity(self):
        # Given: Cache with entity
        cache = make_cache()
        await cache.set("OCG", make_entity("OCG", "ocg_old", confidence=0.8))

        # When: Overwriting with new value
        await cache.set("OCG", make_entity("OCG", "ocg_new", confidence=0.9))

        # Then: Returns updated value
        result = await cache.get("OCG")
        assert result.normalized_value == "ocg_new"

    async def test_get_many_with_empty_list(self):
        # Given: Cache with entities
        cache = make_cache()
        await cache.set("E1", make_entity("E1", "e1"))

        # When: Getting with empty list
        results = await cache.get_many([])

        # Then: Returns empty dict
        assert results == {}

    async def test_set_many_with_empty_dict(self):
        # Given: Empty cache
        cache = make_cache()

        # When: Setting empty dict
        await cache.set_many({})

        # Then: No error, cache still empty
        assert cache.size() == 0


class TestEntityCacheSingleton:
    """Test singleton factory (BDD style)."""

    def setup_method(self):
        # Reset singleton before each test
        cache_module._cache_instance = None

    async def test_get_entity_cache_returns_singleton(self):
        # Given: Multiple calls to factory
        cache1 = get_entity_cache()
        cache2 = get_entity_cache()

        # Then: Same instance
        assert cache1 is cache2

    async def test_singleton_shared_state(self):
        # Given: Entity cached via first reference
        cache1 = get_entity_cache()
        await cache1.set("OCG", make_entity("OCG", "ocg"))

        # When: Accessing via second reference
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
        assert cache2._max_size == original_max_size
