"""Pytest fixtures for orchestration tests."""
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock

from src.article_extractor.models import ExtractedArticleContent
from src.article_extractor.base import ArticleExtractionService
from src.article_extractor.service import DefaultArticleExtractionService
from src.orchestration.service import PipelineOrchestrationService


@pytest.fixture
def sample_extracted_content() -> ExtractedArticleContent:
    """Sample article about corruption for testing."""
    return ExtractedArticleContent(
        title="OCG Launches Investigation into Ministry Contract",
        full_text="The Office of the Contractor General has launched an investigation into alleged irregularities in a multi-million dollar contract awarded by the Ministry of Education. The probe follows reports of procurement violations and concerns about contractor qualifications. The investigation will examine whether proper procedures were followed in the tendering process and if there was any improper influence in the contract award.",
        author="Staff Reporter",
        published_date=datetime(2025, 12, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_extraction_service(sample_extracted_content: ExtractedArticleContent) -> Mock:
    """Mock extraction service that returns sample content."""
    service = Mock(spec=ArticleExtractionService)
    service.extract_article_content = Mock(return_value=sample_extracted_content)
    return service


@pytest.fixture
def orchestration_service_with_mock_extractor(
    mock_extraction_service: Mock,
) -> PipelineOrchestrationService:
    """
    Service with mocked extraction but real classification and persistence.

    This fixture is used for integration tests that:
    - Mock extraction (to avoid fetching real URLs)
    - Use real classification service (makes LLM calls)
    - Use real persistence service (writes to database)
    """
    return PipelineOrchestrationService(
        extraction_service=mock_extraction_service,
        # classification_service uses default (real LLM calls)
        # persistence_service uses default (real database)
    )
