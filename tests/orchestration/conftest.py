"""Pytest fixtures for orchestration tests."""
import pytest
import pytest_asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock

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
    service.extract_article_content = AsyncMock(return_value=sample_extracted_content)
    return service


@pytest_asyncio.fixture(scope="session")
async def global_db_config_pool(
    test_database_url: str, run_migrations: None
) -> AsyncGenerator[None, None]:
    """Initialize the module-level db_config singleton for lazy-connection tests.

    PipelineOrchestrationService._step_store uses the global db_config singleton
    when conn=None (lazy acquisition). The db_pool fixture creates a local
    DatabaseConfig instance, so the singleton's pool must be initialized separately.
    """
    from config.database import db_config as global_db_config

    database_url = test_database_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )
    global_db_config.database_url = database_url
    await global_db_config.create_pool(min_size=2, max_size=10)
    yield
    await global_db_config.close_pool()


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
