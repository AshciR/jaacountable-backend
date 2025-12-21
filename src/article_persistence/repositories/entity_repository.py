from pathlib import Path
from datetime import datetime, timezone
import aiosql
import asyncpg

from src.article_persistence.models.domain import Entity


class EntityRepository:
    """Repository for entity database operations using aiosql."""

    def __init__(self):
        """Initialize the repository and load SQL queries."""
        queries_path = Path(__file__).parent.parent / "queries"
        self.queries = aiosql.from_path(str(queries_path), "asyncpg")

    async def find_by_normalized_name(
        self,
        conn: asyncpg.Connection,
        normalized_name: str,
    ) -> Entity | None:
        """
        Find entity by normalized name for deduplication.

        Args:
            conn: Database connection to use for the query
            normalized_name: Normalized entity name to search for

        Returns:
            Entity | None: Entity if found, None otherwise
        """
        result = await self.queries.find_entity_by_normalized_name(
            conn,
            normalized_name=normalized_name,
        )

        if result is None:
            return None

        return Entity.model_validate(dict(result))

    async def insert_entity(
        self,
        conn: asyncpg.Connection,
        entity: Entity,
    ) -> Entity:
        """
        Insert new entity with both name and normalized_name.

        Args:
            conn: Database connection to use for the query
            entity: Entity to insert (id will be ignored, created_at optional)

        Returns:
            Entity: Created entity with database-generated id

        Raises:
            asyncpg.UniqueViolationError: If normalized_name already exists
            ValueError: If entity data fails validation
        """
        result = await self.queries.insert_entity(
            conn,
            name=entity.name,
            normalized_name=entity.normalized_name,
            created_at=entity.created_at,
        )

        return Entity.model_validate(dict(result))

    async def find_entities_by_article_id(
        self,
        conn: asyncpg.Connection,
        article_id: int,
    ) -> list[Entity]:
        """
        Find all entities linked to a specific article.

        Args:
            conn: Database connection to use for the query
            article_id: Article ID to find entities for

        Returns:
            list[Entity]: List of entities (empty if none found)
        """
        results = await self.queries.find_entities_by_article_id(
            conn,
            article_id=article_id,
        )

        return [Entity.model_validate(dict(row)) for row in results]

    async def find_article_ids_by_entity_id(
        self,
        conn: asyncpg.Connection,
        entity_id: int,
    ) -> list[int]:
        """
        Find all article IDs linked to a specific entity.

        Args:
            conn: Database connection to use for the query
            entity_id: Entity ID to find articles for

        Returns:
            list[int]: List of article IDs (empty if none found)
        """
        results = await self.queries.find_article_ids_by_entity_id(
            conn,
            entity_id=entity_id,
        )

        return [row['article_id'] for row in results]
