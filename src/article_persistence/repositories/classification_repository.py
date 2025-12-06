"""Repository for classification database operations."""
import aiosql
from pathlib import Path
import asyncpg

from src.article_persistence.models.domain import Classification


class ClassificationRepository:
    """Repository for classification database operations using aiosql."""

    def __init__(self):
        """Initialize the repository and load SQL queries."""
        # Load queries from the queries directory
        queries_path = Path(__file__).parent.parent / "queries"
        self.queries = aiosql.from_path(str(queries_path), "asyncpg")

    async def insert_classification(
        self,
        conn: asyncpg.Connection,
        classification: Classification,
    ) -> Classification:
        """
        Insert a new classification into the database.

        Args:
            conn: Database connection to use for the query
            classification: Classification model with validated data

        Returns:
            Classification: The inserted classification with database-generated id

        Raises:
            asyncpg.ForeignKeyViolationError: If article_id does not exist
            ValueError: If classification data fails validation
        """
        # Classification model handles validation and provides defaults
        result = await self.queries.insert_classification(
            conn,
            article_id=classification.article_id,
            classifier_type=classification.classifier_type,
            confidence_score=classification.confidence_score,
            reasoning=classification.reasoning,
            classified_at=classification.classified_at,
            model_name=classification.model_name,
            is_verified=classification.is_verified,
            verified_at=classification.verified_at,
            verified_by=classification.verified_by,
        )

        # Convert asyncpg.Record to Classification model
        return Classification.model_validate(dict(result))
