"""Tests for PostgresArticlePersistenceService."""
import pytest
from datetime import datetime, timezone
import asyncpg
from unittest.mock import AsyncMock, MagicMock

from src.article_persistence.service import PostgresArticlePersistenceService
from src.article_persistence.models.domain import ArticleStorageResult, Classification
from src.article_persistence.repositories.article_repository import ArticleRepository
from src.article_persistence.repositories.classification_repository import ClassificationRepository
from src.article_extractor.models import ExtractedArticleContent
from src.article_classification.models import ClassificationResult, ClassifierType


class TestStoreArticleWithClassificationsHappyPath:
    """Happy path tests for storing articles with classifications."""

    async def test_store_article_with_single_classification_succeeds(
        self,
        service: PostgresArticlePersistenceService,
        db_connection: asyncpg.Connection,
        sample_extracted_content: ExtractedArticleContent,
        sample_classification_results: list[ClassificationResult],
    ):
        # Given: Valid article content and classification
        url = "https://jamaica-gleaner.com/article/news/test-12345"
        section = "news"

        # When: Storing article with classifications
        result = await service.store_article_with_classifications(
            conn=db_connection,
            extracted=sample_extracted_content,
            url=url,
            section=section,
            relevant_classifications=sample_classification_results,
            news_source_id=1,
        )

        # Then: Article is stored successfully
        assert isinstance(result, ArticleStorageResult)
        assert result.stored is True
        assert result.article_id is not None
        assert result.classification_count == 1
        assert result.article is not None
        assert len(result.classifications) == 1

        # Verify article fields
        assert result.article.id == result.article_id
        assert result.article.url == url
        assert result.article.title == sample_extracted_content.title
        assert result.article.section == section

        # Verify classification fields
        classification = result.classifications[0]
        assert classification.id is not None
        assert classification.article_id == result.article_id
        assert classification.classifier_type == "CORRUPTION"
        assert classification.confidence_score == 0.9

    async def test_store_article_with_multiple_classifications_succeeds(
        self,
        service: PostgresArticlePersistenceService,
        db_connection: asyncpg.Connection,
        sample_extracted_content: ExtractedArticleContent,
    ):
        # Given: Article with multiple classification results
        url = "https://jamaica-gleaner.com/article/news/test-multi-class"
        section = "news"
        multiple_classifications = [
            ClassificationResult(
                is_relevant=True,
                confidence=0.85,
                reasoning="OCG investigation",
                key_entities=["OCG"],
                classifier_type=ClassifierType.CORRUPTION,
                model_name="gpt-4o-mini",
            ),
            ClassificationResult(
                is_relevant=True,
                confidence=0.75,
                reasoning="Hurricane relief funds mismanagement",
                key_entities=["ODPEM"],
                classifier_type=ClassifierType.HURRICANE_RELIEF,
                model_name="gpt-4o-mini",
            ),
        ]

        # When: Storing article with multiple classifications
        result = await service.store_article_with_classifications(
            conn=db_connection,
            extracted=sample_extracted_content,
            url=url,
            section=section,
            relevant_classifications=multiple_classifications,
            news_source_id=1,
        )

        # Then: All classifications are stored
        assert result.stored is True
        assert result.classification_count == 2
        assert len(result.classifications) == 2
        assert result.classifications[0].classifier_type == "CORRUPTION"
        assert result.classifications[1].classifier_type == "HURRICANE_RELIEF"

    async def test_store_article_with_zero_classifications_succeeds(
        self,
        service: PostgresArticlePersistenceService,
        db_connection: asyncpg.Connection,
        sample_extracted_content: ExtractedArticleContent,
    ):
        # Given: Article with no classifications
        url = "https://jamaica-gleaner.com/article/news/test-no-class"
        section = "news"

        # When: Storing article with empty classifications list
        result = await service.store_article_with_classifications(
            conn=db_connection,
            extracted=sample_extracted_content,
            url=url,
            section=section,
            relevant_classifications=[],
            news_source_id=1,
        )

        # Then: Article is stored without classifications
        assert result.stored is True
        assert result.article_id is not None
        assert result.classification_count == 0
        assert result.classifications == []


class TestStoreArticleWithClassificationsDuplicates:
    """Tests for duplicate article handling."""

    async def test_duplicate_url_returns_stored_false(
        self,
        service: PostgresArticlePersistenceService,
        db_connection: asyncpg.Connection,
        sample_extracted_content: ExtractedArticleContent,
        sample_classification_results: list[ClassificationResult],
    ):
        # Given: An article already exists in database
        url = "https://jamaica-gleaner.com/article/news/duplicate-test"
        section = "news"

        # First insertion
        await service.store_article_with_classifications(
            conn=db_connection,
            extracted=sample_extracted_content,
            url=url,
            section=section,
            relevant_classifications=sample_classification_results,
        )

        # When: Attempting to store same URL again
        result = await service.store_article_with_classifications(
            conn=db_connection,
            extracted=sample_extracted_content,
            url=url,
            section=section,
            relevant_classifications=sample_classification_results,
        )

        # Then: Returns duplicate result
        assert result.stored is False
        assert result.article_id is None
        assert result.classification_count == 0
        assert result.article is None
        assert result.classifications == []

    async def test_duplicate_does_not_store_classifications(
        self,
        service: PostgresArticlePersistenceService,
        db_connection: asyncpg.Connection,
        sample_extracted_content: ExtractedArticleContent,
        sample_classification_results: list[ClassificationResult],
    ):
        # Given: An article exists
        url = "https://jamaica-gleaner.com/article/news/dup-no-class"
        section = "news"

        first_result = await service.store_article_with_classifications(
            conn=db_connection,
            extracted=sample_extracted_content,
            url=url,
            section=section,
            relevant_classifications=sample_classification_results,
        )

        # When: Attempting duplicate with different classifications
        different_classifications = [
            ClassificationResult(
                is_relevant=True,
                confidence=0.95,
                reasoning="Different reasoning",
                key_entities=["Different Entity"],
                classifier_type=ClassifierType.HURRICANE_RELIEF,
                model_name="gpt-4o-mini",
            )
        ]

        duplicate_result = await service.store_article_with_classifications(
            conn=db_connection,
            extracted=sample_extracted_content,
            url=url,
            section=section,
            relevant_classifications=different_classifications,
        )

        # Then: Duplicate not stored, original classification count unchanged
        assert duplicate_result.stored is False
        assert first_result.classification_count == 1  # Original unchanged


class TestStoreArticleWithClassificationsEdgeCases:
    """Edge case tests."""

    async def test_article_with_special_characters_in_url(
        self,
        service: PostgresArticlePersistenceService,
        db_connection: asyncpg.Connection,
        sample_extracted_content: ExtractedArticleContent,
        sample_classification_results: list[ClassificationResult],
    ):
        # Given: URL with special characters
        url = "https://jamaica-gleaner.com/article/news/test?param=value&foo=bar#section"
        section = "news"

        # When: Storing article with special URL
        result = await service.store_article_with_classifications(
            conn=db_connection,
            extracted=sample_extracted_content,
            url=url,
            section=section,
            relevant_classifications=sample_classification_results,
        )

        # Then: Article stored successfully
        assert result.stored is True
        assert result.article.url == url


class TestStoreArticleWithClassificationsTransactionRollback:
    """Tests for transaction rollback and data consistency."""

    async def test_classification_failure_rolls_back_article(
        self,
        db_connection: asyncpg.Connection,
        sample_extracted_content: ExtractedArticleContent,
        sample_classification_results: list[ClassificationResult],
    ):
        # Given: A service with a mock classification repository that will fail
        article_repo = ArticleRepository()

        # Create mock classification repository that raises exception
        mock_classification_repo = MagicMock(spec=ClassificationRepository)
        mock_classification_repo.insert_classification = AsyncMock(
            side_effect=Exception("Simulated database error during classification insert")
        )

        service = PostgresArticlePersistenceService(
            article_repo=article_repo,
            classification_repo=mock_classification_repo,
        )

        url = "https://jamaica-gleaner.com/article/news/rollback-test"
        section = "news"

        # When: Attempting to store article with classifications that will fail
        with pytest.raises(Exception, match="Simulated database error"):
            await service.store_article_with_classifications(
                conn=db_connection,
                extracted=sample_extracted_content,
                url=url,
                section=section,
                relevant_classifications=sample_classification_results,
                news_source_id=1,
            )

        # Then: Article should NOT exist in database (transaction rolled back)
        # Verify by trying to query the article directly
        query = "SELECT COUNT(*) FROM articles WHERE url = $1"
        count = await db_connection.fetchval(query, url)
        assert count == 0, "Article should not exist after transaction rollback"

    async def test_multiple_classifications_partial_failure_rolls_back_all(
        self,
        db_connection: asyncpg.Connection,
        sample_extracted_content: ExtractedArticleContent,
    ):
        # Given: A service with mock classification repo that fails on second insert
        article_repo = ArticleRepository()

        # Mock returns success for first call, raises exception for second call
        mock_classification_repo = MagicMock(spec=ClassificationRepository)
        mock_classification_repo.insert_classification = AsyncMock(
            side_effect=[
                # First classification succeeds
                Classification(
                    id=1,
                    article_id=1,
                    classifier_type="CORRUPTION",
                    confidence_score=0.85,
                    reasoning="First classification",
                    model_name="gpt-4o-mini",
                ),
                # Second classification fails
                Exception("Simulated failure on second classification"),
            ]
        )

        service = PostgresArticlePersistenceService(
            article_repo=article_repo,
            classification_repo=mock_classification_repo,
        )

        url = "https://jamaica-gleaner.com/article/news/partial-failure-test"
        section = "news"

        # Two classifications - one should succeed, one should fail
        multiple_classifications = [
            ClassificationResult(
                is_relevant=True,
                confidence=0.85,
                reasoning="First classification",
                key_entities=["OCG"],
                classifier_type=ClassifierType.CORRUPTION,
                model_name="gpt-4o-mini",
            ),
            ClassificationResult(
                is_relevant=True,
                confidence=0.75,
                reasoning="Second classification that will fail",
                key_entities=["ODPEM"],
                classifier_type=ClassifierType.HURRICANE_RELIEF,
                model_name="gpt-4o-mini",
            ),
        ]

        # When: Attempting to store with partial failure
        with pytest.raises(Exception, match="Simulated failure on second classification"):
            await service.store_article_with_classifications(
                conn=db_connection,
                extracted=sample_extracted_content,
                url=url,
                section=section,
                relevant_classifications=multiple_classifications,
                news_source_id=1,
            )

        # Then: Neither article nor any classifications should exist (full rollback)
        article_query = "SELECT COUNT(*) FROM articles WHERE url = $1"
        article_count = await db_connection.fetchval(article_query, url)
        assert article_count == 0, "Article should not exist after transaction rollback"

        # Verify no classifications exist either
        classification_query = """
            SELECT COUNT(*) FROM classifications c
            JOIN articles a ON c.article_id = a.id
            WHERE a.url = $1
        """
        classification_count = await db_connection.fetchval(classification_query, url)
        assert classification_count == 0, "No classifications should exist after transaction rollback"


@pytest.fixture
def service() -> PostgresArticlePersistenceService:
    """Create service instance."""
    return PostgresArticlePersistenceService()


@pytest.fixture
def sample_extracted_content() -> ExtractedArticleContent:
    """Create sample extracted content."""
    return ExtractedArticleContent(
        title="OCG Launches Investigation into Ministry Contract",
        full_text="The Office of the Contractor General has launched an investigation into alleged irregularities in a multi-million dollar contract awarded by the Ministry of Education. The probe follows reports of procurement violations and concerns about contractor qualifications.",
        author="Staff Reporter",
        published_date=datetime(2025, 12, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_classification_results() -> list[ClassificationResult]:
    """Create sample classification results."""
    return [
        ClassificationResult(
            is_relevant=True,
            confidence=0.9,
            reasoning="Article discusses OCG investigation into government contract irregularities",
            key_entities=["OCG", "Ministry of Education"],
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
    ]
