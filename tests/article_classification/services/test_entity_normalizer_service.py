"""Unit tests for EntityNormalizerService."""
import pytest
import json
from unittest.mock import AsyncMock, Mock
from pydantic import ValidationError

from src.article_classification.services.entity_normalizer_service import EntityNormalizerService
from src.article_classification.models import NormalizedEntity


class TestEntityNormalizerServiceHappyPath:
    """Test successful normalization scenarios (BDD style)."""

    async def test_normalize_single_entity_succeeds(
        self, mock_runner_single_entity: AsyncMock, mock_session_service: AsyncMock
    ):
        # Given: EntityNormalizerService with mocked dependencies
        normalizer_service = EntityNormalizerService(
            runner=mock_runner_single_entity,
            session_service=mock_session_service
        )

        # When: Normalizing a single entity
        result = await normalizer_service.normalize(["Hon. Ruel Reid"])

        # Then: Returns correct NormalizedEntity
        assert len(result) == 1
        assert isinstance(result[0], NormalizedEntity)
        assert result[0].original_value == "Hon. Ruel Reid"
        assert result[0].normalized_value == "ruel_reid"
        assert result[0].confidence == 0.95
        assert result[0].reason == "Removed title 'Hon.' and standardized format"
        assert result[0].context == ""

    async def test_normalize_multiple_entities_succeeds(
        self, mock_runner_multiple_entities: AsyncMock, mock_session_service: AsyncMock
    ):
        # Given: EntityNormalizerService with mocked dependencies
        normalizer_service = EntityNormalizerService(
            runner=mock_runner_multiple_entities,
            session_service=mock_session_service
        )

        # When: Normalizing multiple entities
        result = await normalizer_service.normalize(["Hon. Ruel Reid", "OCG", "Ministry of Education"])

        # Then: Returns all normalized entities
        assert len(result) == 3
        assert all(isinstance(e, NormalizedEntity) for e in result)
        assert result[0].normalized_value == "ruel_reid"
        assert result[1].normalized_value == "ocg"
        assert result[2].normalized_value == "ministry_of_education"

    async def test_normalize_creates_session(
        self, mock_runner_single_entity: AsyncMock, mock_session_service: AsyncMock
    ):
        # Given: EntityNormalizerService
        normalizer_service = EntityNormalizerService(
            runner=mock_runner_single_entity,
            session_service=mock_session_service
        )

        # When: Normalizing
        await normalizer_service.normalize(["Test Entity"])

        # Then: Session service creates a session
        mock_session_service.create_session.assert_called_once_with(
            app_name="jaccountable_backend",
            user_id="entity_normalizer"
        )


class TestEntityNormalizerServiceValidation:
    """Test validation and error handling (BDD style)."""

    async def test_empty_entities_list_raises_error(self):
        # Given: EntityNormalizerService
        normalizer_service = EntityNormalizerService()

        # When/Then: Empty entities list raises ValueError
        with pytest.raises(ValueError, match="entities list cannot be empty"):
            await normalizer_service.normalize([])

    async def test_invalid_json_response_raises_error(
        self, mock_runner_invalid_json: AsyncMock, mock_session_service: AsyncMock
    ):
        # Given: EntityNormalizerService with agent returning invalid JSON
        normalizer_service = EntityNormalizerService(
            runner=mock_runner_invalid_json,
            session_service=mock_session_service
        )

        # When/Then: Raises JSONDecodeError
        with pytest.raises(json.JSONDecodeError):
            await normalizer_service.normalize(["Test"])


# Fixtures

@pytest.fixture
def mock_session() -> Mock:
    """Mock Google ADK Session."""
    session = Mock()
    session.id = "test-session-123"
    session.user_id = "entity_normalizer"
    return session


@pytest.fixture
def mock_session_service(mock_session: Mock) -> AsyncMock:
    """Mock InMemorySessionService."""
    service = AsyncMock()
    service.create_session = AsyncMock(return_value=mock_session)
    return service


@pytest.fixture
def mock_event_single_entity() -> Mock:
    """Mock event with single normalized entity."""
    event = Mock()
    event.is_final_response = Mock(return_value=True)
    event.content = Mock()
    event.content.parts = [
        Mock(text=json.dumps({
            "normalized_entities": [
                {
                    "original_value": "Hon. Ruel Reid",
                    "normalized_value": "ruel_reid",
                    "confidence": 0.95,
                    "reason": "Removed title 'Hon.' and standardized format"
                }
            ],
            "model_name": "gpt-5-nano"
        }))
    ]
    event.actions = None
    return event


@pytest.fixture
def mock_event_multiple_entities() -> Mock:
    """Mock event with multiple normalized entities."""
    event = Mock()
    event.is_final_response = Mock(return_value=True)
    event.content = Mock()
    event.content.parts = [
        Mock(text=json.dumps({
            "normalized_entities": [
                {
                    "original_value": "Hon. Ruel Reid",
                    "normalized_value": "ruel_reid",
                    "confidence": 0.95,
                    "reason": "Removed title and standardized"
                },
                {
                    "original_value": "OCG",
                    "normalized_value": "ocg",
                    "confidence": 1.0,
                    "reason": "Lowercased acronym"
                },
                {
                    "original_value": "Ministry of Education",
                    "normalized_value": "ministry_of_education",
                    "confidence": 0.90,
                    "reason": "Standardized government entity"
                }
            ],
            "model_name": "gpt-5-nano"
        }))
    ]
    event.actions = None
    return event


@pytest.fixture
def mock_event_invalid_json() -> Mock:
    """Mock event with invalid JSON response."""
    event = Mock()
    event.is_final_response = Mock(return_value=True)
    event.content = Mock()
    event.content.parts = [Mock(text="Not valid JSON")]
    event.actions = None
    return event


@pytest.fixture
def mock_runner_single_entity(mock_event_single_entity: Mock) -> AsyncMock:
    """Mock Google ADK Runner for single entity."""
    runner = AsyncMock()

    async def async_event_generator():
        yield mock_event_single_entity

    runner.run_async = Mock(side_effect=lambda **kwargs: async_event_generator())
    return runner


@pytest.fixture
def mock_runner_multiple_entities(mock_event_multiple_entities: Mock) -> AsyncMock:
    """Mock Google ADK Runner for multiple entities."""
    runner = AsyncMock()

    async def async_event_generator():
        yield mock_event_multiple_entities

    runner.run_async = Mock(side_effect=lambda **kwargs: async_event_generator())
    return runner


@pytest.fixture
def mock_runner_invalid_json(mock_event_invalid_json: Mock) -> AsyncMock:
    """Mock Google ADK Runner with invalid JSON response."""
    runner = AsyncMock()

    async def async_event_generator():
        yield mock_event_invalid_json

    runner.run_async = Mock(side_effect=lambda **kwargs: async_event_generator())
    return runner
