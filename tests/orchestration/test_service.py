"""Tests for PipelineOrchestrationService."""
import pytest
from unittest.mock import Mock, AsyncMock
import asyncpg

from src.orchestration.service import PipelineOrchestrationService
from src.article_extractor.models import ExtractedArticleContent
from src.article_extractor.base import ArticleExtractionService
from src.article_classification.models import ClassificationResult, ClassifierType
from src.article_classification.services.classification_service import ClassificationService
from src.article_persistence.service import PostgresArticlePersistenceService
from src.article_persistence.models.domain import ArticleStorageResult


class TestProcessArticleIntegrationHappyPath:
    """Integration tests for happy path scenarios with real LLM + database."""

    @pytest.mark.external
    @pytest.mark.integration
    async def test_process_relevant_article_full_pipeline_succeeds(
        self,
        orchestration_service_with_mock_extractor: PipelineOrchestrationService,
        db_connection: asyncpg.Connection,
        sample_extracted_content: ExtractedArticleContent,
    ):
        # Given: A corruption-related article (sample_extracted_content)
        url = "https://jamaica-gleaner.com/article/news/test-corruption-123"
        section = "news"

        # When: Processing through full pipeline
        result = await orchestration_service_with_mock_extractor.process_article(
            conn=db_connection,
            url=url,
            section=section,
        )

        # Then: Article classified as relevant and stored
        assert result.extracted is True
        assert result.classified is True
        assert result.relevant is True
        assert result.stored is True
        assert result.article_id is not None
        assert result.classification_count >= 1
        assert len(result.classification_results) >= 1
        assert result.error is None

        # Verify classification details
        corruption_classification = next(
            (
                r
                for r in result.classification_results
                if r.classifier_type == ClassifierType.CORRUPTION
            ),
            None,
        )
        assert corruption_classification is not None
        assert corruption_classification.is_relevant is True
        assert corruption_classification.confidence >= 0.7


class TestProcessArticleEdgeCases:
    """Unit tests for edge cases and error scenarios with mocks."""

    async def test_duplicate_url_not_stored_again(
        self,
        sample_extracted_content: ExtractedArticleContent,
    ):
        # Given: Mock services with duplicate article
        mock_extraction = Mock(spec=ArticleExtractionService)
        mock_extraction.extract_article_content = Mock(
            return_value=sample_extracted_content
        )

        mock_classification = Mock(spec=ClassificationService)
        mock_classification.classify = AsyncMock(
            return_value=[
                ClassificationResult(
                    is_relevant=True,
                    confidence=0.9,
                    reasoning="Corruption investigation involving government contract",
                    classifier_type=ClassifierType.CORRUPTION,
                    model_name="gpt-4o-mini",
                    key_entities=["OCG", "Ministry of Education"],
                )
            ]
        )

        mock_persistence = Mock(spec=PostgresArticlePersistenceService)
        mock_persistence.store_article_with_classifications = AsyncMock(
            return_value=ArticleStorageResult(
                stored=False,  # Duplicate
                article_id=None,
                classification_count=0,
                article=None,
                classifications=[],
            )
        )

        service = PipelineOrchestrationService(
            extraction_service=mock_extraction,
            classification_service=mock_classification,
            persistence_service=mock_persistence,
        )

        mock_conn = Mock()
        url = "https://jamaica-gleaner.com/article/news/duplicate"
        section = "news"

        # When: Processing duplicate article
        result = await service.process_article(
            conn=mock_conn,
            url=url,
            section=section,
        )

        # Then: Not stored (duplicate)
        assert result.extracted is True
        assert result.classified is True
        assert result.relevant is True
        assert result.stored is False
        assert result.article_id is None
        assert result.classification_count == 0

    async def test_extraction_failure_returns_error_result(self):
        # Given: Mock services with extraction failure
        mock_extraction = Mock(spec=ArticleExtractionService)
        mock_extraction.extract_article_content = Mock(
            side_effect=Exception("Failed to fetch URL: 404 Not Found")
        )

        service = PipelineOrchestrationService(
            extraction_service=mock_extraction,
        )

        mock_conn = Mock()
        url = "https://jamaica-gleaner.com/article/news/missing-404"
        section = "news"

        # When: Processing article with extraction failure
        result = await service.process_article(
            conn=mock_conn,
            url=url,
            section=section,
        )

        # Then: Error result returned, pipeline stopped
        assert result.extracted is False
        assert result.classified is False
        assert result.relevant is False
        assert result.stored is False
        assert result.article_id is None
        assert result.error is not None
        assert "Failed to extract article" in result.error

    async def test_classification_failure_returns_error_result(
        self,
        sample_extracted_content: ExtractedArticleContent,
    ):
        # Given: Mock services with classification failure
        mock_extraction = Mock(spec=ArticleExtractionService)
        mock_extraction.extract_article_content = Mock(
            return_value=sample_extracted_content
        )

        mock_classification = Mock(spec=ClassificationService)
        mock_classification.classify = AsyncMock(
            side_effect=Exception("LLM API timeout")
        )

        service = PipelineOrchestrationService(
            extraction_service=mock_extraction,
            classification_service=mock_classification,
        )

        mock_conn = Mock()
        url = "https://jamaica-gleaner.com/article/news/test"
        section = "news"

        # When: Processing with classification failure
        result = await service.process_article(
            conn=mock_conn,
            url=url,
            section=section,
        )

        # Then: Error result with classified=False
        assert result.extracted is True
        assert result.classified is False
        assert result.relevant is False
        assert result.stored is False
        assert result.error is not None
        assert "Failed to classify article" in result.error

    async def test_storage_failure_returns_error_result(
        self,
        sample_extracted_content: ExtractedArticleContent,
    ):
        # Given: Mock services with storage failure
        mock_extraction = Mock(spec=ArticleExtractionService)
        mock_extraction.extract_article_content = Mock(
            return_value=sample_extracted_content
        )

        mock_classification = Mock(spec=ClassificationService)
        mock_classification.classify = AsyncMock(
            return_value=[
                ClassificationResult(
                    is_relevant=True,
                    confidence=0.9,
                    reasoning="Corruption investigation",
                    classifier_type=ClassifierType.CORRUPTION,
                    model_name="gpt-4o-mini",
                    key_entities=["OCG"],
                )
            ]
        )

        mock_persistence = Mock(spec=PostgresArticlePersistenceService)
        mock_persistence.store_article_with_classifications = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        service = PipelineOrchestrationService(
            extraction_service=mock_extraction,
            classification_service=mock_classification,
            persistence_service=mock_persistence,
        )

        mock_conn = Mock()
        url = "https://jamaica-gleaner.com/article/news/test"
        section = "news"

        # When: Processing with storage failure
        result = await service.process_article(
            conn=mock_conn,
            url=url,
            section=section,
        )

        # Then: Error result with stored=False
        assert result.extracted is True
        assert result.classified is True
        assert result.relevant is True
        assert result.stored is False
        assert result.error is not None
        assert "Failed to store article" in result.error

    async def test_article_not_relevant_not_stored(
        self,
        sample_extracted_content: ExtractedArticleContent,
    ):
        # Given: Mock services with low-confidence classification
        mock_extraction = Mock(spec=ArticleExtractionService)
        mock_extraction.extract_article_content = Mock(
            return_value=sample_extracted_content
        )

        mock_classification = Mock(spec=ClassificationService)
        mock_classification.classify = AsyncMock(
            return_value=[
                ClassificationResult(
                    is_relevant=False,  # Not relevant
                    confidence=0.3,
                    reasoning="Sports article about track championship",
                    classifier_type=ClassifierType.CORRUPTION,
                    model_name="gpt-4o-mini",
                    key_entities=[],
                )
            ]
        )

        service = PipelineOrchestrationService(
            extraction_service=mock_extraction,
            classification_service=mock_classification,
        )

        mock_conn = Mock()
        url = "https://jamaica-gleaner.com/article/sports/test"
        section = "sports"

        # When: Processing non-relevant article
        result = await service.process_article(
            conn=mock_conn,
            url=url,
            section=section,
        )

        # Then: Not stored, no error
        assert result.extracted is True
        assert result.classified is True
        assert result.relevant is False
        assert result.stored is False
        assert result.article_id is None
        assert result.classification_count == 0
        assert result.error is None
