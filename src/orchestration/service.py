"""
Orchestration service for article processing pipeline.

Coordinates the full workflow: Extract → Classify → Filter → Store
"""
import logging
import asyncpg

from src.article_extractor.models import ExtractedArticleContent
from src.article_extractor.base import ArticleExtractionService
from src.article_extractor.service import DefaultArticleExtractionService
from src.article_classification.models import ClassificationInput, ClassificationResult, NormalizedEntity
from src.article_classification.services.classification_service import ClassificationService
from src.article_classification.classifiers.corruption_classifier import CorruptionClassifier
from src.article_classification.services.entity_normalizer_service import EntityNormalizerService
from src.article_classification.converters import extracted_content_to_classification_input
from src.article_classification.utils import filter_relevant_classifications
from src.article_persistence.service import PostgresArticlePersistenceService
from .models import OrchestrationResult


logger = logging.getLogger(__name__)


class PipelineOrchestrationService:
    """
    Orchestrates the full article processing pipeline.

    This service coordinates the workflow:
    1. Extract article content from URL
    2. Convert to classification input
    3. Classify article with multiple classifiers
    4. Filter relevant classifications
    5. Store article and classifications if relevant

    The service uses dependency injection for testability and flexibility.
    All dependencies default to production implementations if not provided.

    Example:
        # Default configuration (production)
        service = PipelineOrchestrationService()
        async with db_config.connection() as conn:
            result = await service.process_article(
                conn=conn,
                url="https://jamaica-gleaner.com/article/news/...",
                section="news",
            )

        # Custom configuration (testing)
        service = PipelineOrchestrationService(
            extraction_service=MockExtractionService(),
            classification_service=MockClassificationService(),
            persistence_service=MockPersistenceService(),
        )
    """

    def __init__(
        self,
        extraction_service: ArticleExtractionService | None = None,
        classification_service: ClassificationService | None = None,
        persistence_service: PostgresArticlePersistenceService | None = None,
        entity_normalizer: EntityNormalizerService | None = None,
    ):
        """
        Initialize orchestration service with dependencies.

        Args:
            extraction_service: Service for extracting article content
                (default: DefaultArticleExtractionService())
            classification_service: Service for classifying articles
                (default: ClassificationService with CorruptionClassifier)
            persistence_service: Service for storing articles and classifications
                (default: PostgresArticlePersistenceService())
            entity_normalizer: Service for normalizing entity names
                (default: EntityNormalizerService())
        """
        self.extraction_service = extraction_service or DefaultArticleExtractionService()
        self.classification_service = classification_service or ClassificationService(
            classifiers=[
                CorruptionClassifier(),
            ]
        )
        self.persistence_service = (
            persistence_service or PostgresArticlePersistenceService()
        )
        self.entity_normalizer = entity_normalizer or EntityNormalizerService()

    async def process_article(
        self,
        conn: asyncpg.Connection,
        url: str,
        section: str,
        news_source_id: int = 1,
        min_confidence: float = 0.7,
    ) -> OrchestrationResult:
        """
        Process an article through the full pipeline: Extract → Classify → Store.

        The method handles errors at each stage and returns a comprehensive
        result object. Errors are logged and returned in the result rather
        than propagated as exceptions.

        Args:
            conn: Database connection (caller manages lifecycle)
            url: Article URL to process
            section: Article section/category (e.g., "news", "lead-stories")
            news_source_id: Database ID of news source (default: 1 for Jamaica Gleaner)
            min_confidence: Minimum confidence threshold for relevance (default: 0.7)

        Returns:
            OrchestrationResult with processing outcome and metadata

        Example:
            >>> service = PipelineOrchestrationService()
            >>> async with db_config.connection() as conn:
            ...     result = await service.process_article(
            ...         conn=conn,
            ...         url="https://jamaica-gleaner.com/article/news/...",
            ...         section="news",
            ...     )
            ...     if result.stored:
            ...         print(f"Article {result.article_id} stored")
            ...     elif result.error:
            ...         print(f"Error: {result.error}")
            ...     else:
            ...         print("Article not relevant")
        """
        logger.info(f"Processing article: {url}")

        # Step 1: Extract article content
        success, result = await self._extract_article(
            extraction_service=self.extraction_service,
            url=url,
            section=section,
        )
        if not success:
            return result  # type: ignore
        extracted: ExtractedArticleContent = result  # type: ignore

        # Step 2: Convert to classification input
        success, result = self._convert_to_classification_input(extracted, url, section)
        if not success:
            return result  # type: ignore
        classification_input: ClassificationInput = result  # type: ignore

        # Step 3: Classify article
        success, result = await self._classify_article(
            classification_service=self.classification_service,
            classification_input=classification_input,
            url=url,
            section=section,
        )
        if not success:
            return result  # type: ignore
        classification_results: list[ClassificationResult] = result  # type: ignore

        # Step 4: Filter relevant classifications
        success, result = self._filter_and_check_relevance(
            classification_results, min_confidence, url, section
        )
        if not success:
            return result  # type: ignore
        relevant_results: list[ClassificationResult] = result  # type: ignore

        # Step 4.5: Normalize entities from relevant classifications
        try:
            normalized_entities: list[NormalizedEntity] = await self._normalize_entities(
                entity_normalizer=self.entity_normalizer,
                relevant_classifications=relevant_results,
            )
        except Exception as e:
            logger.error(f"Failed to normalize entities: {e}", exc_info=True)
            # Continue without normalized entities (will be empty list)
            normalized_entities = []

        # Step 5: Store article and classifications
        return await self._store_article(
            persistence_service=self.persistence_service,
            conn=conn,
            extracted=extracted,
            url=url,
            section=section,
            relevant_results=relevant_results,
            classification_results=classification_results,
            normalized_entities=normalized_entities,
            news_source_id=news_source_id,
        )

    async def _extract_article(
        self,
        extraction_service: ArticleExtractionService,
        url: str,
        section: str,
    ) -> tuple[bool, ExtractedArticleContent | OrchestrationResult]:
        """
        Extract article content from URL.

        Args:
            extraction_service: Service for extracting article content
            url: Article URL to extract
            section: Article section (for error result)

        Returns:
            Tuple of (success, result):
            - On success: (True, ExtractedArticleContent)
            - On error: (False, OrchestrationResult with error)
        """
        try:
            extracted = await extraction_service.extract_article_content(url)
            logger.info(f"Extracted: {extracted.title[:100]}...")
            return (True, extracted)
        except Exception as e:
            error_msg = f"Failed to extract article: {e}"
            logger.error(error_msg, exc_info=True)
            return (
                False,
                OrchestrationResult(
                    url=url,
                    section=section,
                    extracted=False,
                    classified=False,
                    relevant=False,
                    stored=False,
                    article_id=None,
                    classification_count=0,
                    classification_results=[],
                    error=error_msg,
                ),
            )

    def _convert_to_classification_input(
        self,
        extracted: ExtractedArticleContent,
        url: str,
        section: str,
    ) -> tuple[bool, ClassificationInput | OrchestrationResult]:
        """
        Convert extracted article content to classification input.

        Args:
            extracted: Extracted article content
            url: Article URL
            section: Article section

        Returns:
            Tuple of (success, result):
            - On success: (True, ClassificationInput)
            - On error: (False, OrchestrationResult with error)
        """
        try:
            classification_input = extracted_content_to_classification_input(
                extracted=extracted,
                url=url,
                section=section,
            )
            return (True, classification_input)
        except Exception as e:
            error_msg = f"Failed to convert to classification input: {e}"
            logger.error(error_msg, exc_info=True)
            return (
                False,
                OrchestrationResult(
                    url=url,
                    section=section,
                    extracted=True,
                    classified=False,
                    relevant=False,
                    stored=False,
                    article_id=None,
                    classification_count=0,
                    classification_results=[],
                    error=error_msg,
                ),
            )

    async def _classify_article(
        self,
        classification_service: ClassificationService,
        classification_input: ClassificationInput,
        url: str,
        section: str,
    ) -> tuple[bool, list[ClassificationResult] | OrchestrationResult]:
        """
        Classify article using classification service.

        Args:
            classification_service: Service for classifying articles
            classification_input: Classification input data
            url: Article URL (for error result)
            section: Article section (for error result)

        Returns:
            Tuple of (success, result):
            - On success: (True, list[ClassificationResult])
            - On error: (False, OrchestrationResult with error)
        """
        try:
            classification_results = await classification_service.classify(
                classification_input
            )
            logger.info(f"Received {len(classification_results)} classification results")

            for result in classification_results:
                logger.info(
                    f"  - {result.classifier_type.value}: "
                    f"relevant={result.is_relevant}, confidence={result.confidence:.2f}"
                )
            return (True, classification_results)
        except Exception as e:
            error_msg = f"Failed to classify article: {e}"
            logger.error(error_msg, exc_info=True)
            return (
                False,
                OrchestrationResult(
                    url=url,
                    section=section,
                    extracted=True,
                    classified=False,
                    relevant=False,
                    stored=False,
                    article_id=None,
                    classification_count=0,
                    classification_results=[],
                    error=error_msg,
                ),
            )

    def _filter_and_check_relevance(
        self,
        classification_results: list[ClassificationResult],
        min_confidence: float,
        url: str,
        section: str,
    ) -> tuple[bool, list[ClassificationResult] | OrchestrationResult]:
        """
        Filter relevant classifications and check if article is relevant.

        Args:
            classification_results: All classification results
            min_confidence: Minimum confidence threshold
            url: Article URL (for result)
            section: Article section (for result)

        Returns:
            Tuple of (success, result):
            - On success (article relevant): (True, list[relevant ClassificationResult])
            - On no relevant results: (False, OrchestrationResult with relevant=False)
            - On error: (False, OrchestrationResult with error)
        """
        try:
            relevant_results = filter_relevant_classifications(
                results=classification_results,
                min_confidence=min_confidence,
            )

            if not relevant_results:
                logger.info("Article is NOT relevant (skipping storage)")
                return (
                    False,
                    OrchestrationResult(
                        url=url,
                        section=section,
                        extracted=True,
                        classified=True,
                        relevant=False,
                        stored=False,
                        article_id=None,
                        classification_count=0,
                        classification_results=classification_results,
                        error=None,
                    ),
                )

            logger.info(
                f"Article IS relevant ({len(relevant_results)} classifiers passed)"
            )
            return (True, relevant_results)
        except Exception as e:
            error_msg = f"Failed to filter classifications: {e}"
            logger.error(error_msg, exc_info=True)
            return (
                False,
                OrchestrationResult(
                    url=url,
                    section=section,
                    extracted=True,
                    classified=True,
                    relevant=False,
                    stored=False,
                    article_id=None,
                    classification_count=0,
                    classification_results=classification_results,
                    error=error_msg,
                ),
            )

    async def _normalize_entities(
        self,
        entity_normalizer: EntityNormalizerService,
        relevant_classifications: list[ClassificationResult],
    ) -> list[NormalizedEntity]:
        """
        Extract and normalize entities from relevant classifications.

        Args:
            entity_normalizer: Service for normalizing entity names
            relevant_classifications: Classifications that passed confidence threshold

        Returns:
            List of NormalizedEntity objects with original/normalized pairs
        """
        # Extract unique entities from all relevant classifications
        unique_entities: set[str] = set()
        for classification in relevant_classifications:
            unique_entities.update(classification.key_entities)

        if not unique_entities:
            logger.info("No entities to normalize (all classifications had empty key_entities)")
            return []

        entity_list = list(unique_entities)
        logger.info(f"Normalizing {len(entity_list)} unique entities")

        # Normalize entities using normalizer service
        normalized: list[NormalizedEntity] = await entity_normalizer.normalize(entity_list)

        logger.info(f"Normalized {len(normalized)} entities")
        return normalized

    async def _store_article(
        self,
        persistence_service: PostgresArticlePersistenceService,
        conn: asyncpg.Connection,
        extracted: ExtractedArticleContent,
        url: str,
        section: str,
        relevant_results: list[ClassificationResult],
        classification_results: list[ClassificationResult],
        normalized_entities: list[NormalizedEntity],
        news_source_id: int,
    ) -> OrchestrationResult:
        """
        Store article and classifications in database.

        Args:
            persistence_service: Service for storing articles and classifications
            conn: Database connection
            extracted: Extracted article content
            url: Article URL
            section: Article section
            relevant_results: Filtered relevant classification results
            classification_results: All classification results (for result metadata)
            normalized_entities: Normalized entities with original/normalized pairs
            news_source_id: News source database ID

        Returns:
            OrchestrationResult with storage outcome
        """
        try:
            storage_result = await persistence_service.store_article_with_classifications(
                conn=conn,
                extracted=extracted,
                url=url,
                section=section,
                relevant_classifications=relevant_results,
                normalized_entities=normalized_entities,
                news_source_id=news_source_id,
            )

            if storage_result.stored:
                logger.info(f"Article stored with ID: {storage_result.article_id}")
                logger.info(
                    f"Stored {storage_result.classification_count} classifications"
                )
                return OrchestrationResult(
                    url=url,
                    section=section,
                    extracted=True,
                    classified=True,
                    relevant=True,
                    stored=True,
                    article_id=storage_result.article_id,
                    classification_count=storage_result.classification_count,
                    classification_results=classification_results,
                    error=None,
                )
            else:
                # Article already exists (duplicate URL)
                logger.info("Article already exists in database (duplicate URL)")
                return OrchestrationResult(
                    url=url,
                    section=section,
                    extracted=True,
                    classified=True,
                    relevant=True,
                    stored=False,
                    article_id=None,
                    classification_count=0,
                    classification_results=classification_results,
                    error=None,
                )

        except Exception as e:
            error_msg = f"Failed to store article: {e}"
            logger.error(error_msg, exc_info=True)
            return OrchestrationResult(
                url=url,
                section=section,
                extracted=True,
                classified=True,
                relevant=True,
                stored=False,
                article_id=None,
                classification_count=0,
                classification_results=classification_results,
                error=error_msg,
            )
