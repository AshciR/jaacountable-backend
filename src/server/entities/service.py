"""Service layer for entity listing."""
import json

import asyncpg

from src.article_persistence.models.domain import EntityListResult
from src.article_persistence.repositories.entity_repository import EntityRepository
from src.cache.cache_interface import CacheBackend
from src.server.entities.schemas import EntityListParams


class EntityListService:
    """Service that delegates entity listing to the repository, with optional caching.

    Caching strategy:
    - All entity listing requests are cached. The parameter space is small
      (sort, since, page, page_size), so hit rates are expected to be high.
    """

    def __init__(
        self,
        repo: EntityRepository | None = None,
        cache: CacheBackend | None = None,
    ):
        self._repo = repo or EntityRepository()
        self._cache = cache

    async def list_entities(
        self,
        conn: asyncpg.Connection,
        params: EntityListParams,
    ) -> tuple[list[EntityListResult], int]:
        """List entities and return results with total count for pagination."""
        if self._cache is None:
            return await self._repo.list_entities(
                conn,
                sort=params.sort,
                since=params.since,
                page=params.page,
                page_size=params.page_size,
            )

        # Check if cache results are available
        cached: tuple[list[EntityListResult], int] | None = await self._get_cached(params)
        if cached is not None:
            return cached

        # No cache hit, make DB call and populate cache
        results, total = await self._repo.list_entities(
            conn,
            sort=params.sort,
            since=params.since,
            page=params.page,
            page_size=params.page_size,
        )
        await self._set_cached(params, results, total)

        return results, total

    async def _get_cached(
        self,
        params: EntityListParams,
    ) -> tuple[list[EntityListResult], int] | None:
        """Return cached entity list results, or None on cache miss."""
        raw = await self._cache.get(self._build_cache_key(params))  # type: ignore[union-attr]
        if raw is None:
            return None
        data = json.loads(raw)
        return (
            [EntityListResult.model_validate(r) for r in data["results"]],
            data["total"],
        )

    async def _set_cached(
        self,
        params: EntityListParams,
        results: list[EntityListResult],
        total: int,
        ttl_seconds: int = 300,
    ) -> None:
        """Serialize and store entity list results in the cache."""
        payload = json.dumps({
            "results": [r.model_dump(mode="json") for r in results],
            "total": total,
        })
        await self._cache.set(self._build_cache_key(params), payload, ttl_seconds=ttl_seconds)  # type: ignore[union-attr]

    @staticmethod
    def _build_cache_key(params: EntityListParams) -> str:
        """Build a deterministic cache key from entity list request parameters."""
        return (
            f"entities:"
            f"s={params.sort}:"
            f"since={params.since}:"
            f"p={params.page}:"
            f"ps={params.page_size}"
        )
