"""Unit tests for InMemoryCache."""
from unittest.mock import patch

import pytest

from src.cache.in_memory import InMemoryCache


class TestInMemoryCacheGetSet:
    """Basic get/set behaviour."""

    async def test_get_returns_none_on_miss(self):
        # Given: an empty cache
        cache = InMemoryCache()

        # When: we get a key that was never set
        result = await cache.get("missing-key")

        # Then: None is returned
        assert result is None

    async def test_set_then_get_returns_value(self):
        # Given: a cache with one entry
        cache = InMemoryCache()
        await cache.set("key", "value", ttl_seconds=60)

        # When: we get the same key
        result = await cache.get("key")

        # Then: the stored value is returned
        assert result == "value"

    async def test_set_overwrites_existing_key(self):
        # Given: a cache with an existing entry
        cache = InMemoryCache()
        await cache.set("key", "original", ttl_seconds=60)
        await cache.set("key", "updated", ttl_seconds=60)

        # When: we get the key
        result = await cache.get("key")

        # Then: the updated value is returned
        assert result == "updated"

    async def test_delete_removes_key(self):
        # Given: a cache with an entry
        cache = InMemoryCache()
        await cache.set("key", "value", ttl_seconds=60)

        # When: we delete the key and then get it
        await cache.delete("key")
        result = await cache.get("key")

        # Then: None is returned
        assert result is None

    async def test_delete_nonexistent_key_does_not_raise(self):
        # Given: an empty cache
        cache = InMemoryCache()

        # When / Then: deleting a missing key does not raise
        await cache.delete("ghost-key")

    async def test_size_reflects_stored_entries(self):
        # Given: a cache with 3 entries
        cache = InMemoryCache()
        for i in range(3):
            await cache.set(f"key-{i}", f"value-{i}", ttl_seconds=60)

        # Then: size returns 3
        assert cache.size() == 3


class TestInMemoryCacheTTL:
    """TTL expiration behaviour."""

    async def test_expired_entry_returns_none(self):
        # Given: a cache entry that is immediately past its TTL
        cache = InMemoryCache()

        # Set the entry with ttl=10s but then advance time by 11s
        with patch("src.cache.in_memory.time") as mock_time:
            mock_time.time.return_value = 1000.0
            await cache.set("key", "value", ttl_seconds=10)

        # When: we read back after 11 seconds
        with patch("src.cache.in_memory.time") as mock_time:
            mock_time.time.return_value = 1011.0
            result = await cache.get("key")

        # Then: the expired entry is treated as a miss
        assert result is None

    async def test_entry_within_ttl_is_returned(self):
        # Given: a cache entry with a 60s TTL
        cache = InMemoryCache()

        with patch("src.cache.in_memory.time") as mock_time:
            mock_time.time.return_value = 1000.0
            await cache.set("key", "value", ttl_seconds=60)

        # When: we read back within the TTL window
        with patch("src.cache.in_memory.time") as mock_time:
            mock_time.time.return_value = 1059.0
            result = await cache.get("key")

        # Then: the value is returned
        assert result == "value"

    async def test_expired_entry_is_removed_from_size(self):
        # Given: a cache entry that expires immediately
        cache = InMemoryCache()

        with patch("src.cache.in_memory.time") as mock_time:
            mock_time.time.return_value = 1000.0
            await cache.set("key", "value", ttl_seconds=1)

        # When: we read back after expiry (triggers lazy eviction)
        with patch("src.cache.in_memory.time") as mock_time:
            mock_time.time.return_value = 1002.0
            await cache.get("key")

        # Then: the entry is no longer in the cache
        assert cache.size() == 0

    async def test_per_entry_ttl_is_respected(self):
        # Given: two entries with different TTLs
        cache = InMemoryCache()

        with patch("src.cache.in_memory.time") as mock_time:
            mock_time.time.return_value = 1000.0
            await cache.set("short", "value_short", ttl_seconds=5)
            await cache.set("long", "value_long", ttl_seconds=100)

        # When: we read back after the short TTL has expired
        with patch("src.cache.in_memory.time") as mock_time:
            mock_time.time.return_value = 1006.0
            short_result = await cache.get("short")
            long_result = await cache.get("long")

        # Then: short-TTL entry is gone, long-TTL entry is still present
        assert short_result is None
        assert long_result == "value_long"


class TestInMemoryCacheLRUEviction:
    """LRU eviction when max_size is reached."""

    async def test_oldest_entry_evicted_when_at_capacity(self):
        # Given: a cache with max_size=2 that is full
        cache = InMemoryCache(max_size=2)
        await cache.set("first", "a", ttl_seconds=600)
        await cache.set("second", "b", ttl_seconds=600)

        # When: we add a third entry
        await cache.set("third", "c", ttl_seconds=600)

        # Then: the first entry was evicted (LRU — least recently used)
        assert await cache.get("first") is None
        assert await cache.get("second") == "b"
        assert await cache.get("third") == "c"

    async def test_recently_accessed_entry_not_evicted(self):
        # Given: a cache with max_size=2
        cache = InMemoryCache(max_size=2)
        await cache.set("first", "a", ttl_seconds=600)
        await cache.set("second", "b", ttl_seconds=600)

        # When: we access "first" (making it recently used) then add a third entry
        await cache.get("first")
        await cache.set("third", "c", ttl_seconds=600)

        # Then: "second" was evicted (now the LRU), "first" was spared
        assert await cache.get("first") == "a"
        assert await cache.get("second") is None
        assert await cache.get("third") == "c"

    async def test_size_does_not_exceed_max_size(self):
        # Given: a cache with max_size=3
        cache = InMemoryCache(max_size=3)

        # When: we add 5 entries
        for i in range(5):
            await cache.set(f"key-{i}", f"val-{i}", ttl_seconds=600)

        # Then: size stays at the max
        assert cache.size() == 3
