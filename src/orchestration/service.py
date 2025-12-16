"""
Orchestration service for article processing pipeline.

Coordinates the full workflow: Extract → Classify → Filter → Store
"""
import logging
import asyncpg

from src.article_extractor.models import ExtractedArticleContent
from src.article_extractor.base import ArticleExtractionService
from src.article_extractor.service import DefaultArticleExtractionService
from src.article_classification.models import ClassificationInput, ClassificationResult
from src.article_classification.service import ClassificationService
from src.article_classification.agents.corruption_classifier import CorruptionClassifier
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
        success, result = self._extract_article(url, section)
        if not success:
            return result  # type: ignore
        extracted = result  # type: ignore

        # Step 2: Convert to classification input
        success, result = self._convert_to_classification_input(extracted, url, section)
        if not success:
            return result  # type: ignore
        classification_input = result  # type: ignore

        # Step 3: Classify article
        success, result = await self._classify_article(classification_input, url, section)
        if not success:
            return result  # type: ignore
        classification_results = result  # type: ignore

        # Step 4: Filter relevant classifications
        success, result = self._filter_and_check_relevance(
            classification_results, min_confidence, url, section
        )
        if not success:
            return result  # type: ignore
        relevant_results = result  # type: ignore

        # Step 5: Store article and classifications
        return await self._store_article(
            conn=conn,
            extracted=extracted,
            url=url,
            section=section,
            relevant_results=relevant_results,
            classification_results=classification_results,
            news_source_id=news_source_id,
        )

    def _extract_article(
        self,
        url: str,
        section: str,
    ) -> tuple[bool, ExtractedArticleContent | OrchestrationResult]:
        """
        Extract article content from URL.

        Args:
            url: Article URL to extract
            section: Article section (for error result)

        Returns:
            Tuple of (success, result):
            - On success: (True, ExtractedArticleContent)
            - On error: (False, OrchestrationResult with error)
        """
        try:
            extracted = self.extraction_service.extract_article_content(url)
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
        classification_input: ClassificationInput,
        url: str,
        section: str,
    ) -> tuple[bool, list[ClassificationResult] | OrchestrationResult]:
        """
        Classify article using classification service.

        Args:
            classification_input: Classification input data
            url: Article URL (for error result)
            section: Article section (for error result)

        Returns:
            Tuple of (success, result):
            - On success: (True, list[ClassificationResult])
            - On error: (False, OrchestrationResult with error)
        """
        try:
            classification_results = await self.classification_service.classify(
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

    async def _store_article(
        self,
        conn: asyncpg.Connection,
        extracted: ExtractedArticleContent,
        url: str,
        section: str,
        relevant_results: list[ClassificationResult],
        classification_results: list[ClassificationResult],
        news_source_id: int,
    ) -> OrchestrationResult:
        """
        Store article and classifications in database.

        Args:
            conn: Database connection
            extracted: Extracted article content
            url: Article URL
            section: Article section
            relevant_results: Filtered relevant classification results
            classification_results: All classification results (for result metadata)
            news_source_id: News source database ID

        Returns:
            OrchestrationResult with storage outcome
        """
        try:
            storage_result = await self.persistence_service.store_article_with_classifications(
                conn=conn,
                extracted=extracted,
                url=url,
                section=section,
                relevant_classifications=relevant_results,
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
