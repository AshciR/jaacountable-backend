"""Service layer for entity listing."""
import asyncpg

from src.article_persistence.models.domain import EntityListResult
from src.article_persistence.repositories.entity_repository import EntityRepository
from src.server.entities.schemas import EntityListParams


class EntityListService:
    """Thin service that delegates entity listing to the repository layer."""

    def __init__(self, repo: EntityRepository | None = None):
        self._repo = repo or EntityRepository()

    async def list_entities(
        self,
        conn: asyncpg.Connection,
        params: EntityListParams,
    ) -> tuple[list[EntityListResult], int]:
        """List entities and return results with total count for pagination."""
        return await self._repo.list_entities(
            conn,
            sort=params.sort,
            since=params.since,
            page=params.page,
            page_size=params.page_size,
        )
