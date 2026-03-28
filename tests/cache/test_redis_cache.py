"""Unit tests for RedisCacheBackend."""
import asyncio

import pytest

from src.cache.redis_cache import RedisCacheBackend


class TestRedisCacheGetSet:
    """Basic get/set behaviour."""

    async def test_get_returns_none_on_miss(self, redis_cache: RedisCacheBackend):
        # Given: an empty cache

        # When: we get a key that was never set
        result = await redis_cache.get("missing-key")

        # Then: None is returned
        assert result is None

    async def test_set_then_get_returns_value(self, redis_cache: RedisCacheBackend):
        # Given: a cache with one entry
        await redis_cache.set("key", "value", ttl_seconds=60)

        # When: we get the same key
        result = await redis_cache.get("key")

        # Then: the stored value is returned
        assert result == "value"

    async def test_set_overwrites_existing_key(self, redis_cache: RedisCacheBackend):
        # Given: a cache with an existing entry
        await redis_cache.set("key", "original", ttl_seconds=60)
        await redis_cache.set("key", "updated", ttl_seconds=60)

        # When: we get the key
        result = await redis_cache.get("key")

        # Then: the updated value is returned
        assert result == "updated"

    async def test_delete_removes_key(self, redis_cache: RedisCacheBackend):
        # Given: a cache with an entry
        await redis_cache.set("key", "value", ttl_seconds=60)

        # When: we delete the key and then get it
        await redis_cache.delete("key")
        result = await redis_cache.get("key")

        # Then: None is returned
        assert result is None

    async def test_delete_nonexistent_key_does_not_raise(
        self, redis_cache: RedisCacheBackend
    ):
        # Given: an empty cache

        # When / Then: deleting a missing key does not raise
        await redis_cache.delete("ghost-key")

    async def test_size_returns_minus_one(self, redis_cache: RedisCacheBackend):
        # Given: a cache with entries
        await redis_cache.set("key-1", "a", ttl_seconds=60)
        await redis_cache.set("key-2", "b", ttl_seconds=60)

        # Then: size returns -1 (not applicable for distributed cache)
        assert redis_cache.size() == -1


class TestRedisCacheTTL:
    """TTL expiration behaviour."""

    async def test_expired_entry_returns_none(self, redis_cache: RedisCacheBackend):
        # Given: a cache entry with a 1-second TTL
        await redis_cache.set("key", "value", ttl_seconds=1)

        # When: we wait for the TTL to expire then read back
        await asyncio.sleep(1.1)
        result = await redis_cache.get("key")

        # Then: the expired entry is treated as a miss
        assert result is None

    async def test_entry_within_ttl_is_returned(self, redis_cache: RedisCacheBackend):
        # Given: a cache entry with a generous TTL
        await redis_cache.set("key", "value", ttl_seconds=60)

        # When: we read back immediately (well within the TTL)
        result = await redis_cache.get("key")

        # Then: the value is returned
        assert result == "value"

    async def test_per_entry_ttl_is_respected(self, redis_cache: RedisCacheBackend):
        # Given: two entries — one with a 1-second TTL, one with a 60-second TTL
        await redis_cache.set("short", "value_short", ttl_seconds=1)
        await redis_cache.set("long", "value_long", ttl_seconds=60)

        # When: we wait for the short TTL to expire
        await asyncio.sleep(1.1)

        # Then: the short-TTL entry is gone, the long-TTL entry is still present
        assert await redis_cache.get("short") is None
        assert await redis_cache.get("long") == "value_long"
