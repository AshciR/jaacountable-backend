"""
Orchestration service for article processing pipeline.

Coordinates the full workflow: Extract → Classify → Filter → Store
"""
import time

import asyncpg
from loguru import logger

from src.article_extractor.models import ExtractedArticleContent
from src.article_extractor.base import ArticleExtractionService
from src.article_extractor.service import DefaultArticleExtractionService
from src.article_classification.models import ClassificationInput, ClassificationResult, NormalizedEntity
from src.article_classification.services.classification_service import ClassificationService
from src.article_classification.classifiers.corruption_classifier import CorruptionClassifier
from src.article_classification.services.entity_normalizer_service import EntityNormalizerService
from src.article_classification.services.in_memory_entity_cache import get_entity_cache
from src.article_classification.converters import extracted_content_to_classification_input
from src.article_classification.utils import filter_relevant_classifications
from src.article_persistence.service import PostgresArticlePersistenceService
from .models import OrchestrationResult


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
        # Inject singleton cache into entity normalizer (production config)
        self.entity_normalizer = entity_normalizer or EntityNormalizerService(
            cache=get_entity_cache()  # Singleton cache shared across all instances
        )

    async def __aenter__(self):
        """
        Initialize extraction service with HTTP connection pooling.

        If the extraction service supports async context manager (has __aenter__),
        this method initializes it for connection pooling during batch processing.

        Returns:
            Self to enable async context manager pattern
        """
        if hasattr(self.extraction_service, "__aenter__"):
            await self.extraction_service.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Clean up extraction service resources.

        If the extraction service supports async context manager (has __aexit__),
        this method closes HTTP connections and cleans up resources.

        Args:
            exc_type: Exception type if an error occurred
            exc_val: Exception value if an error occurred
            exc_tb: Exception traceback if an error occurred
        """
        if hasattr(self.extraction_service, "__aexit__"):
            await self.extraction_service.__aexit__(exc_type, exc_val, exc_tb)

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

        Emits ONE canonical log line at the end with complete telemetry.

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
        # Initialize telemetry dictionary for canonical log line
        telemetry: dict[str, str | int | float] = {
            "url": url,
            "section": section,
            "news_source_id": news_source_id,
            "min_confidence": min_confidence,
        }

        # Start total pipeline timing
        pipeline_start = time.perf_counter()

        try:
            # Step 1: Extract article content
            extraction_start = time.perf_counter()
            success, result = await self._extract_article(
                extraction_service=self.extraction_service,
                url=url,
                section=section,
            )
            telemetry["extraction_duration_ms"] = round((time.perf_counter() - extraction_start) * 1000, 2)

            if not success:
                telemetry.update({
                    "extracted": False,
                    "classified": False,
                    "relevant": False,
                    "stored": False,
                    "error": result.error,  # type: ignore
                    "error_stage": "extraction",
                })
                telemetry["total_duration_ms"] = round((time.perf_counter() - pipeline_start) * 1000, 2)
                logger.bind(**telemetry).error("canonical-log-line")
                return result  # type: ignore

            extracted: ExtractedArticleContent = result  # type: ignore
            telemetry.update({
                "extracted": True,
                "extracted_title": extracted.title[:100],  # Truncate to 100 chars
            })

            # Step 2: Convert to classification input
            success, result = self._convert_to_classification_input(extracted, url, section)
            if not success:
                telemetry.update({
                    "classified": False,
                    "relevant": False,
                    "stored": False,
                    "error": result.error,  # type: ignore
                    "error_stage": "conversion",
                })
                telemetry["total_duration_ms"] = round((time.perf_counter() - pipeline_start) * 1000, 2)
                logger.bind(**telemetry).error("canonical-log-line")
                return result  # type: ignore

            classification_input: ClassificationInput = result  # type: ignore

            # Step 3: Classify article
            classification_start = time.perf_counter()
            success, result = await self._classify_article(
                classification_service=self.classification_service,
                classification_input=classification_input,
                url=url,
                section=section,
            )
            telemetry["classification_duration_ms"] = round((time.perf_counter() - classification_start) * 1000, 2)

            if not success:
                telemetry.update({
                    "classified": False,
                    "relevant": False,
                    "stored": False,
                    "error": result.error,  # type: ignore
                    "error_stage": "classification",
                })
                telemetry["total_duration_ms"] = round((time.perf_counter() - pipeline_start) * 1000, 2)
                logger.bind(**telemetry).error("canonical-log-line")
                return result  # type: ignore

            classification_results: list[ClassificationResult] = result  # type: ignore
            telemetry.update({
                "classified": True,
                "classifier_count": len(classification_results),
            })

            # Add individual classifier results to telemetry
            for cls_result in classification_results:
                prefix = cls_result.classifier_type.value.lower()
                telemetry[f"{prefix}_relevant"] = cls_result.is_relevant
                telemetry[f"{prefix}_confidence"] = cls_result.confidence
                telemetry[f"{prefix}_model"] = cls_result.model_name

            # Step 4: Filter relevant classifications
            success, result = self._filter_and_check_relevance(
                classification_results, min_confidence, url, section
            )
            if not success:
                # Article not relevant OR filtering error
                result_obj: OrchestrationResult = result  # type: ignore
                telemetry.update({
                    "relevant": result_obj.relevant,
                    "stored": False,
                    "relevant_classifiers": 0,
                })
                if result_obj.error:
                    telemetry["error"] = result_obj.error
                    telemetry["error_stage"] = "filtering"

                telemetry["total_duration_ms"] = round((time.perf_counter() - pipeline_start) * 1000, 2)

                # Use appropriate log level
                if result_obj.error:
                    logger.bind(**telemetry).error("canonical-log-line")
                else:
                    logger.bind(**telemetry).info("canonical-log-line")

                return result  # type: ignore

            relevant_results: list[ClassificationResult] = result  # type: ignore
            telemetry.update({
                "relevant": True,
                "relevant_classifiers": len(relevant_results),
            })

            # Step 4.5: Normalize entities from relevant classifications
            entity_normalization_start = time.perf_counter()
            try:
                normalized_entities: list[NormalizedEntity] = await self._normalize_entities(
                    entity_normalizer=self.entity_normalizer,
                    relevant_classifications=relevant_results,
                )
                telemetry["entity_count"] = len(normalized_entities)
            except Exception as e:
                # Non-fatal error - continue without entities
                logger.bind(url=url, section=section, error_type=type(e).__name__).warning(
                    f"Entity normalization failed - continuing: {e}"
                )
                normalized_entities = []
                telemetry["entity_count"] = 0
                telemetry["entity_normalization_error"] = str(e)

            telemetry["entity_normalization_duration_ms"] = round((time.perf_counter() - entity_normalization_start) * 1000, 2)

            # Step 5: Store article and classifications
            storage_start = time.perf_counter()
            storage_result = await self._store_article(
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
            telemetry["storage_duration_ms"] = round((time.perf_counter() - storage_start) * 1000, 2)

            # Add storage results to telemetry
            telemetry.update({
                "stored": storage_result.stored,
                "article_id": storage_result.article_id,
                "classification_count": storage_result.classification_count,
            })

            if storage_result.error:
                telemetry["error"] = storage_result.error
                telemetry["error_stage"] = "storage"

            # Calculate total duration
            telemetry["total_duration_ms"] = round((time.perf_counter() - pipeline_start) * 1000, 2)

            # Emit ONE canonical log line with all telemetry
            if storage_result.error:
                logger.bind(**telemetry).error("canonical-log-line")
            elif not storage_result.stored:
                # Duplicate article case
                logger.bind(**telemetry).warning("canonical-log-line")
            else:
                logger.bind(**telemetry).info("canonical-log-line")

            return storage_result

        except Exception as e:
            # Unexpected error - emit canonical log with whatever we collected
            telemetry.update({
                "error": str(e),
                "error_type": type(e).__name__,
                "error_stage": "unexpected",
                "total_duration_ms": round((time.perf_counter() - pipeline_start) * 1000, 2),
            })
            logger.bind(**telemetry).error("canonical-log-line", exc_info=True)
            raise

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
            return (True, extracted)
        except Exception as e:
            error_msg = f"Failed to extract article: {e}"
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
            return (True, classification_results)
        except Exception as e:
            error_msg = f"Failed to classify article: {e}"
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

            return (True, relevant_results)
        except Exception as e:
            error_msg = f"Failed to filter classifications: {e}"
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
            return []

        entity_list = list(unique_entities)

        # Normalize entities using normalizer service
        normalized: list[NormalizedEntity] = await entity_normalizer.normalize(entity_list)

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
