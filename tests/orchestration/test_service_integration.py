import asyncpg
import pytest

from src.article_classification.models import ClassifierType
from src.article_extractor.models import ExtractedArticleContent
from src.orchestration.service import PipelineOrchestrationService


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
