from datetime import date, datetime, timezone
from pathlib import Path
import aiosql
import asyncpg

from src.article_persistence.models.domain import Entity, EntityListResult


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

    async def list_entities(
        self,
        conn: asyncpg.Connection,
        sort: str = "latest",
        since: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[EntityListResult], int]:
        """
        List entities with aggregated article counts and recency data.

        Args:
            conn: Database connection to use for the query
            sort: "latest" orders by most recent article date; "most_found" orders by article count
            since: When provided, scope article_count and last_seen_date to articles on/after this date
            page: 1-indexed page number
            page_size: Number of results per page

        Returns:
            Tuple of (results, total_count) for pagination
        """
        params: list = []
        param_idx = 0

        def track(value) -> str:
            nonlocal param_idx
            param_idx += 1
            params.append(value)
            return f"${param_idx}"

        where_parts = ["a.published_date IS NOT NULL"]
        if since is not None:
            since_dt = datetime(since.year, since.month, since.day, tzinfo=timezone.utc)
            where_parts.append(f"a.published_date >= {track(since_dt)}")
        where_sql = "WHERE " + " AND ".join(where_parts)

        order_col = "last_seen_date" if sort == "latest" else "article_count"

        offset = (page - 1) * page_size
        limit_param = track(page_size)
        offset_param = track(offset)

        main_sql = f"""
            SELECT
                e.name,
                e.normalized_name,
                COUNT(ae.article_id) AS article_count,
                MAX(a.published_date) AS last_seen_date
            FROM entities e
            JOIN article_entities ae ON ae.entity_id = e.id
            JOIN articles a ON a.id = ae.article_id
            {where_sql}
            GROUP BY e.id, e.name, e.normalized_name
            ORDER BY {order_col} DESC
            LIMIT {limit_param} OFFSET {offset_param}
        """

        count_params = params[:-2]
        count_sql = f"""
            SELECT COUNT(DISTINCT e.id)
            FROM entities e
            JOIN article_entities ae ON ae.entity_id = e.id
            JOIN articles a ON a.id = ae.article_id
            {where_sql}
        """

        rows = await conn.fetch(main_sql, *params)
        total_count = await conn.fetchval(count_sql, *count_params)

        return [EntityListResult.model_validate(dict(row)) for row in rows], (total_count or 0)

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
