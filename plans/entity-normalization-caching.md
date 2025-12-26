# Entity Normalization Caching Implementation Plan

## Overview

Add a caching layer to `EntityNormalizerService` to reduce redundant LLM API calls when normalizing entity names. The cache stores mappings from original entity names (e.g., "Hon. Ruel Reid") to their normalized forms (e.g., "ruel_reid") with metadata.

**Design Decisions:**
- **Cache granularity**: Per-entity (cache each entity name individually for max hit rate)
- **TTL**: Permanent (entity normalization is deterministic, no expiration)
- **Architecture**: Inside EntityNormalizerService (encapsulation, testability)
- **Fallback**: Fail-soft (fall back to LLM if cache fails, log warning)
- **Initial implementation**: In-memory dict-based cache
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
  → Check cache for all 3 entities
  → Cache HIT: "Hon. Ruel Reid" (from previous article)
  → Cache MISS: "OCG", "Ministry of Education"
  → Create session + call LLM for ONLY 2 uncached entities
  → Populate cache with new results
  → Combine cached + new results in original order
  → Return complete list[NormalizedEntity]
```

**Key Benefits:**
- Reduces LLM API costs (cache hits = no API call)
- 10-100x faster for cached entities (1ms vs 500-2000ms)
- Consistent normalization across articles
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

    Cache Key: Entity original_value (e.g., "Hon. Ruel Reid")
    Cache Value: Complete NormalizedEntity object
    TTL: Permanent (entity normalization rules don't change)
    """

    async def get(self, entity_name: str) -> NormalizedEntity | None:
        """Retrieve normalized entity from cache."""
        ...

    async def set(self, entity_name: str, normalized: NormalizedEntity) -> None:
        """Store normalized entity in cache."""
        ...

    async def get_many(self, entity_names: list[str]) -> dict[str, NormalizedEntity]:
        """Retrieve multiple entities (batch operation). Returns dict of hits only."""
        ...

    async def set_many(self, normalizations: dict[str, NormalizedEntity]) -> None:
        """Store multiple entities (batch operation)."""
        ...
```

**Import update (line 4)**:
```python
from .models import ClassificationInput, ClassificationResult, NormalizedEntity
```

### Step 2: Implement InMemoryEntityCache

**File**: `src/article_classification/services/in_memory_entity_cache.py` (NEW)

Create dict-based cache implementation:

```python
"""In-memory cache implementation for entity normalization."""
import asyncio
import logging
from src.article_classification.models import NormalizedEntity

logger = logging.getLogger(__name__)


class InMemoryEntityCache:
    """
    In-memory dict-based cache for normalized entities.

    Thread Safety: Uses asyncio.Lock (not threading.Lock) for async context
    TTL: None (permanent storage)
    Size Limits: None for MVP
    """

    def __init__(self):
        self._cache: dict[str, NormalizedEntity] = {}
        self._lock = asyncio.Lock()
        logger.info("Initialized InMemoryEntityCache")

    async def get(self, entity_name: str) -> NormalizedEntity | None:
        async with self._lock:
            result = self._cache.get(entity_name)
            if result:
                logger.debug(f"Cache HIT: '{entity_name}' → '{result.normalized_value}'")
            else:
                logger.debug(f"Cache MISS: '{entity_name}'")
            return result

    async def set(self, entity_name: str, normalized: NormalizedEntity) -> None:
        async with self._lock:
            self._cache[entity_name] = normalized
            logger.debug(f"Cache SET: '{entity_name}' → '{normalized.normalized_value}'")

    async def get_many(self, entity_names: list[str]) -> dict[str, NormalizedEntity]:
        async with self._lock:
            results = {name: self._cache[name] for name in entity_names if name in self._cache}
            logger.debug(f"Cache get_many: {len(results)} hits, {len(entity_names) - len(results)} misses")
            return results

    async def set_many(self, normalizations: dict[str, NormalizedEntity]) -> None:
        async with self._lock:
            self._cache.update(normalizations)
            logger.debug(f"Cache set_many: stored {len(normalizations)} entities")

    def size(self) -> int:
        """Get cache size (for testing/debugging)."""
        return len(self._cache)

    async def clear(self) -> None:
        """Clear cache (for testing)."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cache cleared: removed {count} entities")
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
    return [all_results[e] for e in entities]
```

### Step 4: Update PipelineOrchestrationService

**File**: `src/orchestration/service.py`

**4.1 Import Update (after line 15)**:
```python
from src.article_classification.services.in_memory_entity_cache import InMemoryEntityCache
```

**4.2 Update Constructor (modify lines 57-86)**:

Replace this line:
```python
self.entity_normalizer = entity_normalizer or EntityNormalizerService()
```

With:
```python
# Inject cache into entity normalizer (default production config)
self.entity_normalizer = entity_normalizer or EntityNormalizerService(
    cache=InMemoryEntityCache()  # Cache enabled by default
)
```

### Step 5: Update Module Exports

**File**: `src/article_classification/services/__init__.py`

Add export:
```python
from .in_memory_entity_cache import InMemoryEntityCache

__all__ = ["InMemoryEntityCache"]
```

### Step 6: Create Tests

**File**: `tests/article_classification/services/test_in_memory_entity_cache.py` (NEW)

Create comprehensive tests following BDD style:

```python
"""Unit tests for InMemoryEntityCache."""
import pytest
from src.article_classification.services.in_memory_entity_cache import InMemoryEntityCache
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


class TestInMemoryEntityCacheEdgeCases:
    """Test edge cases (BDD style)."""

    async def test_case_sensitive_keys(self):
        # Given: Cache with case-sensitive key
        cache = InMemoryEntityCache()
        await cache.set("Hon. Ruel Reid", NormalizedEntity(original_value="Hon. Ruel Reid", normalized_value="ruel_reid", confidence=0.95, reason="Test"))

        # When: Getting with different case
        result = await cache.get("hon. ruel reid")

        # Then: Cache miss
        assert result is None

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

        # Then: All removed
        assert cache.size() == 0
        assert await cache.get("E1") is None
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

- [ ] `test_in_memory_entity_cache.py`: 10+ tests (cache operations, edge cases)
- [ ] `test_entity_normalizer_service.py`: Add 6+ tests (cache integration)
- [ ] Run full test suite: `uv run pytest tests/ -m "not integration" -v`
- [ ] Verify all tests pass
- [ ] Manual test: Process article with repeated entities, check logs for cache hits

## Future Redis Migration (No Code Changes Needed)

When ready for production Redis cache:

1. **Add dependency**: `redis` to `pyproject.toml`
2. **Implement RedisEntityCache**:
   ```python
   class RedisEntityCache:  # Implements EntityCache protocol
       async def get(self, entity_name: str) -> NormalizedEntity | None:
           key = f"entity_norm:{entity_name}"
           cached_json = await self.redis.get(key)
           return NormalizedEntity.model_validate_json(cached_json) if cached_json else None
       # ... implement other methods
   ```
3. **Swap implementation** in `PipelineOrchestrationService.__init__`:
   ```python
   from .redis_entity_cache import RedisEntityCache

   self.entity_normalizer = entity_normalizer or EntityNormalizerService(
       cache=RedisEntityCache()  # Just change this line!
   )
   ```

No changes needed in `EntityNormalizerService` due to protocol abstraction.

## Critical Files Summary

| File | Action | Key Changes |
|------|--------|-------------|
| `src/article_classification/base.py` | Edit | Add `EntityCache` protocol after line 104 |
| `src/article_classification/services/in_memory_entity_cache.py` | Create | Implement dict-based cache with asyncio.Lock |
| `src/article_classification/services/entity_normalizer_service.py` | Edit | Add cache parameter, update `normalize()` logic |
| `src/orchestration/service.py` | Edit | Inject `InMemoryEntityCache()` in constructor |
| `src/article_classification/services/__init__.py` | Edit | Export `InMemoryEntityCache` |
| `tests/article_classification/services/test_in_memory_entity_cache.py` | Create | 10+ unit tests for cache |
| `tests/article_classification/services/test_entity_normalizer_service.py` | Edit | Add 6+ cache integration tests |

## Expected Performance Impact

**Before Caching:**
- Article with 5 entities → 1 LLM call (~500-2000ms)
- 10 articles with same entities → 10 LLM calls (~5-20 seconds total)

**After Caching:**
- First article: 1 LLM call + 5 cache writes (~500-2000ms)
- Subsequent articles: 5 cache hits + 0 LLM calls (~5ms total)
- **10-100x speedup** for cached entities
- **Significant cost savings** on LLM API calls

## Success Criteria

- All tests pass (unit + integration)
- Cache hit rate >80% for repeated entities in logs
- No LLM calls when all entities cached
- Cache failures don't break normalization (fail-soft)
- Backwards compatible (cache=None works as before)
