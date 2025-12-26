"""
Article persistence service layer.

Provides high-level operations for storing articles and classifications.
"""
import logging
import asyncpg
from datetime import datetime, timezone

from asyncpg import UniqueViolationError

from src.article_extractor.models import ExtractedArticleContent
from src.article_classification.models import ClassificationResult, NormalizedEntity
from .converters import (
    extracted_content_to_article,
    classification_result_to_classification,
)
from .models.domain import ArticleStorageResult, Entity, ArticleEntity
from .repositories.article_repository import ArticleRepository
from .repositories.classification_repository import ClassificationRepository
from .repositories.entity_repository import EntityRepository
from .repositories.article_entity_repository import ArticleEntityRepository


logger = logging.getLogger(__name__)


class PostgresArticlePersistenceService:
    """
    PostgreSQL implementation of ArticlePersistenceService Protocol.

    Stores articles and classifications in PostgreSQL database
    with transactional guarantees. The service manages transaction
    boundaries while the caller manages connection lifecycle.
    """

    def __init__(
        self,
        article_repo: ArticleRepository | None = None,
        classification_repo: ClassificationRepository | None = None,
        entity_repo: EntityRepository | None = None,
        article_entity_repo: ArticleEntityRepository | None = None,
    ):
        """
        Initialize service with repository dependencies.

        Args:
            article_repo: Article repository (default: creates new instance)
            classification_repo: Classification repository (default: creates new instance)
            entity_repo: Entity repository (default: creates new instance)
            article_entity_repo: Article-entity junction repository (default: creates new instance)
        """
        self.article_repo = article_repo or ArticleRepository()
        self.classification_repo = classification_repo or ClassificationRepository()
        self.entity_repo = entity_repo or EntityRepository()
        self.article_entity_repo = article_entity_repo or ArticleEntityRepository()

    async def store_article_with_classifications(
        self,
        conn: asyncpg.Connection,
        extracted: ExtractedArticleContent,
        url: str,
        section: str,
        relevant_classifications: list[ClassificationResult],
        normalized_entities: list[NormalizedEntity],
        news_source_id: int = 1,
    ) -> ArticleStorageResult:
        """
        Store an article with its classifications in a single transaction.

        The caller must provide a connection, but this method manages the
        transaction to ensure article and classifications are stored atomically.

        Args:
            conn: Database connection (caller manages lifecycle)
            extracted: Extracted article content from ArticleExtractionService
            url: Original article URL
            section: Article section (e.g., "news", "lead-stories")
            relevant_classifications: List of relevant classification results.
                Must contain at least one classification.
            normalized_entities: List of normalized entities with original/normalized pairs
            news_source_id: Database ID of news source (default: 1 for Jamaica Gleaner)

        Returns:
            ArticleStorageResult with storage outcome and metadata

        Raises:
            ValueError: If relevant_classifications is empty
            UniqueViolationError: If article URL already exists (caught internally)
            Exception: For other database errors

        Example:
            >>> service = PostgresArticlePersistenceService()
            >>> async with db_config.connection() as conn:
            ...     result = await service.store_article_with_classifications(
            ...         conn=conn,
            ...         extracted=extracted_content,
            ...         url=url,
            ...         section="news",
            ...         relevant_classifications=results,
            ...         normalized_entities=normalized_entities,
            ...     )
        """
        # Validate that at least one classification is provided
        if not relevant_classifications:
            raise ValueError(
                "Cannot store article without classifications. "
                "At least one relevant classification is required. "
                "Article relevance should be determined before calling this method."
            )

        # Convert to Article domain model
        article = extracted_content_to_article(
            extracted=extracted,
            url=url,
            section=section,
            news_source_id=news_source_id,
        )

        try:
            async with conn.transaction():
                # Insert article (get article_id)
                stored_article = await self.article_repo.insert_article(conn, article)
                logger.info(f"Article stored with ID: {stored_article.id}")

                # Insert classifications
                stored_classifications = await self._store_classifications_for_article(
                    conn=conn,
                    article_id=stored_article.id,  # type: ignore
                    classifications=relevant_classifications,
                )

                # Store normalized entities with original/normalized pairs
                stored_entities = await self._store_entities_for_article(
                    conn=conn,
                    article_id=stored_article.id,  # type: ignore
                    normalized_entities=normalized_entities,
                )

                return ArticleStorageResult(
                    stored=True,
                    article_id=stored_article.id,
                    classification_count=len(stored_classifications),
                    article=stored_article,
                    classifications=stored_classifications,
                    entity_count=len(stored_entities),
                    entities=stored_entities,
                )

        except UniqueViolationError:
            # Article already exists (URL unique constraint)
            logger.info(f"Article already exists, skipping: {url}")
            return ArticleStorageResult(
                stored=False,
                article_id=None,
                classification_count=0,
                article=None,
                classifications=[],
                entity_count=0,
                entities=[],
            )

    async def _store_classifications_for_article(
        self,
        conn: asyncpg.Connection,
        article_id: int,
        classifications: list[ClassificationResult],
    ) -> list:
        """
        Store classifications for an article.

        Args:
            conn: Database connection (within active transaction)
            article_id: Database ID of article
            classifications: List of classification results to store

        Returns:
            List of stored Classification models with database-generated IDs
        """
        stored_classifications = []
        for result in classifications:
            classification = classification_result_to_classification(
                result=result,
                article_id=article_id,
            )
            stored_classification = await self.classification_repo.insert_classification(
                conn, classification
            )
            stored_classifications.append(stored_classification)
            logger.info(
                f"Classification stored (type: {result.classifier_type.value}, "
                f"confidence: {result.confidence:.2f})"
            )

        return stored_classifications

    async def _store_entities_for_article(
        self,
        conn: asyncpg.Connection,
        article_id: int,
        normalized_entities: list[NormalizedEntity],
    ) -> list[Entity]:
        """
        Store normalized entities and link them to the article.

        This method:
        1. Deduplicates entities by normalized_value
        2. Stores entities with BOTH original_value (name) and normalized_value (normalized_name)
        3. Links entities to article via article_entities junction table

        Args:
            conn: Database connection (within active transaction)
            article_id: Database ID of article
            normalized_entities: List of NormalizedEntity objects from normalizer

        Returns:
            List of Entity models that were stored (created or existing)
        """
        if not normalized_entities:
            logger.info("No entities to store (normalized_entities is empty)")
            return []

        # Step 1: Deduplicate by normalized_value (keep first occurrence for original_value)
        seen_normalized: dict[str, NormalizedEntity] = {}
        for entity in normalized_entities:
            if entity.normalized_value not in seen_normalized:
                seen_normalized[entity.normalized_value] = entity

        unique_entities = list(seen_normalized.values())
        logger.info(
            f"Deduplicating: {len(normalized_entities)} → {len(unique_entities)} unique entities"
        )

        # Step 2: Store entities (find or create by normalized_name)
        stored_entities: list[Entity] = []
        entity_id_mapping: dict[str, int] = {}  # normalized_value → entity_id

        for norm_entity in unique_entities:
            # Try to find existing entity by normalized name
            existing_entity = await self.entity_repo.find_by_normalized_name(
                conn, norm_entity.normalized_value
            )

            if existing_entity:
                entity_id_mapping[norm_entity.normalized_value] = existing_entity.id  # type: ignore
                stored_entities.append(existing_entity)
                logger.debug(
                    f"Entity '{norm_entity.normalized_value}' already exists "
                    f"(id={existing_entity.id}, name={existing_entity.name})"
                )
            else:
                # Create new entity with BOTH original and normalized names
                new_entity = Entity(
                    name=norm_entity.original_value,  # Store ORIGINAL name
                    normalized_name=norm_entity.normalized_value,  # Store NORMALIZED name
                    created_at=datetime.now(timezone.utc),
                )
                created_entity = await self.entity_repo.insert_entity(conn, new_entity)
                entity_id_mapping[norm_entity.normalized_value] = created_entity.id  # type: ignore
                stored_entities.append(created_entity)
                logger.info(
                    f"Created new entity: name='{norm_entity.original_value}' "
                    f"normalized_name='{norm_entity.normalized_value}' "
                    f"(id={created_entity.id}, confidence={norm_entity.confidence})"
                )

        # Step 3: Link entities to article
        # For now, we don't track which classifier extracted each entity
        # (that information is lost when we normalize all entities together)
        # Use "CORRUPTION" as default classifier_type for all links
        links_created = 0
        for norm_entity in unique_entities:
            entity_id = entity_id_mapping[norm_entity.normalized_value]

            article_entity = ArticleEntity(
                article_id=article_id,
                entity_id=entity_id,
                classifier_type="CORRUPTION",  # Default for now
                created_at=datetime.now(timezone.utc),
            )

            try:
                await self.article_entity_repo.link_article_to_entity(conn, article_entity)
                links_created += 1
                logger.debug(
                    f"Linked entity '{norm_entity.normalized_value}' to article {article_id}"
                )
            except UniqueViolationError:
                logger.debug(
                    f"Link already exists: article={article_id}, "
                    f"entity={entity_id}, classifier=CORRUPTION"
                )

        logger.info(
            f"Entity storage complete: {len(stored_entities)} entities, "
            f"{links_created} article-entity links created"
        )

        return stored_entities
