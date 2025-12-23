"""Tests for CorruptionClassifierAdapter."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from src.article_classification.agents.corruption_classifier import (
    CorruptionClassifier,
)
from src.article_classification.models import (
    ClassificationInput,
    ClassificationResult,
    ClassifierType,
)


class TestCorruptionAdapterHappyPath:
    """Test successful classification scenarios."""

    async def test_classify_corruption_article_returns_relevant(
        self, sample_corruption_article: ClassificationInput, mock_runner: AsyncMock, mock_session_service: AsyncMock
    ):
        # Given: Adapter with mocked dependencies
        classifier = CorruptionClassifier(
            runner=mock_runner,
            session_service=mock_session_service,
        )

        # When: Classifying an article
        result = await classifier.classify(sample_corruption_article)

        # Then: Returns ClassificationResult with expected values
        assert isinstance(result, ClassificationResult)
        assert result.is_relevant is True
        assert result.confidence == 0.9
        assert result.classifier_type == ClassifierType.CORRUPTION

    async def test_classify_creates_new_session(
        self, sample_corruption_article: ClassificationInput, mock_runner: AsyncMock, mock_session_service: AsyncMock
    ):
        # Given: Adapter with mocked session service
        classifier = CorruptionClassifier(
            runner=mock_runner,
            session_service=mock_session_service,
        )

        # When: Classifying an article
        await classifier.classify(sample_corruption_article)

        # Then: Session service creates new session
        mock_session_service.create_session.assert_called_once_with(
            app_name="jaccountable_backend",
            user_id="classifier_corruption"
        )

    async def test_classify_calls_runner_with_correct_params(
        self, sample_corruption_article: ClassificationInput, mock_runner: AsyncMock, mock_session_service: AsyncMock, mock_session: Mock
    ):
        # Given: Adapter with mocked runner
        classifier = CorruptionClassifier(
            runner=mock_runner,
            session_service=mock_session_service,
        )

        # When: Classifying an article
        await classifier.classify(sample_corruption_article)

        # Then: Runner.run_async called with session context
        mock_runner.run_async.assert_called_once()
        call_kwargs = mock_runner.run_async.call_args.kwargs
        assert call_kwargs["user_id"] == "classifier_corruption"
        assert call_kwargs["session_id"] == "test-session-123"


class TestCorruptionAdapterPromptBuilding:
    """Test _build_prompt() method."""

    async def test_build_prompt_includes_all_article_fields(self, sample_corruption_article: ClassificationInput):
        # Given: Adapter instance
        classifier = CorruptionClassifier()

        # When: Building prompt
        prompt = classifier._build_prompt(sample_corruption_article)

        # Then: Prompt includes all article fields
        assert sample_corruption_article.title in prompt
        assert sample_corruption_article.url in prompt
        assert sample_corruption_article.section in prompt
        assert sample_corruption_article.full_text in prompt

    async def test_build_prompt_with_none_published_date(self):
        # Given: Article without published_date
        article = ClassificationInput(
            url="https://example.com/test",
            title="Test",
            section="news",
            full_text="A" * 60,
            published_date=None,
        )
        classifier = CorruptionClassifier()

        # When: Building prompt
        prompt = classifier._build_prompt(article)

        # Then: Prompt shows 'Unknown' for date
        assert "Unknown" in prompt

    async def test_build_prompt_includes_json_instruction(self, sample_corruption_article: ClassificationInput):
        # Given: Adapter instance
        classifier = CorruptionClassifier()

        # When: Building prompt
        prompt = classifier._build_prompt(sample_corruption_article)

        # Then: Prompt asks for JSON response
        assert "JSON" in prompt or "json" in prompt
        assert "ClassificationResult" in prompt


class TestCorruptionAdapterEventProcessing:
    """Test _call_agent_async() event handling."""

    async def test_call_agent_extracts_final_response(
        self, mock_runner: AsyncMock, mock_session: Mock
    ):
        # Given: Adapter with mocked runner
        classifier = CorruptionClassifier(runner=mock_runner)
        prompt = "Test prompt"

        # When: Calling agent async
        response = await classifier._call_agent_async(
            prompt, mock_runner, mock_session.user_id, mock_session.id
        )

        # Then: Returns text from final event
        assert "is_relevant" in response
        assert "confidence" in response

    async def test_call_agent_handles_agent_escalation(self, mock_session: Mock):
        # Given: Runner with escalation event
        escalation_event = Mock()
        escalation_event.is_final_response = Mock(return_value=True)
        escalation_event.content = None
        escalation_event.actions = Mock()
        escalation_event.actions.escalate = True
        escalation_event.error_message = "Test error"

        runner = AsyncMock()

        async def error_generator():
            yield escalation_event

        runner.run_async = Mock(side_effect=lambda **kwargs: error_generator())

        classifier = CorruptionClassifier(runner=runner)

        # When: Calling agent async
        response = await classifier._call_agent_async(
            "test", runner, mock_session.user_id, mock_session.id
        )

        # Then: Returns escalation message
        assert "escalated" in response.lower()
        assert "Test error" in response

    async def test_call_agent_handles_multiple_events(self, mock_session: Mock):
        # Given: Runner with multiple non-final events before final
        event1 = Mock()
        event1.is_final_response = Mock(return_value=False)

        event2 = Mock()
        event2.is_final_response = Mock(return_value=False)

        final_event = Mock()
        final_event.is_final_response = Mock(return_value=True)
        final_event.content = Mock()
        final_event.content.parts = [Mock(text='{"is_relevant": false}')]

        runner = AsyncMock()

        async def multi_event_generator():
            yield event1
            yield event2
            yield final_event

        runner.run_async = Mock(side_effect=lambda **kwargs: multi_event_generator())

        classifier = CorruptionClassifier(runner=runner)

        # When: Calling agent async
        response = await classifier._call_agent_async(
            "test", runner, mock_session.user_id, mock_session.id
        )

        # Then: Returns only final event text
        assert "is_relevant" in response


class TestCorruptionAdapterJsonParsing:
    """Test JSON response parsing."""

    async def test_classify_parses_valid_json(
        self, sample_corruption_article: ClassificationInput, mock_runner: AsyncMock, mock_session_service: AsyncMock
    ):
        # Given: Adapter with valid JSON response
        classifier = CorruptionClassifier(
            runner=mock_runner,
            session_service=mock_session_service,
        )

        # When: Classifying article
        result = await classifier.classify(sample_corruption_article)

        # Then: Result is properly parsed ClassificationResult
        assert isinstance(result, ClassificationResult)
        assert result.model_name == "gpt-5-nano"

    async def test_classify_raises_on_invalid_json(
        self, sample_corruption_article: ClassificationInput, mock_session_service: AsyncMock
    ):
        # Given: Runner returning invalid JSON
        bad_event = Mock()
        bad_event.is_final_response = Mock(return_value=True)
        bad_event.content = Mock()
        bad_event.content.parts = [Mock(text='{"invalid_json"')]

        runner = AsyncMock()

        async def bad_json_generator():
            yield bad_event

        runner.run_async = Mock(side_effect=lambda **kwargs: bad_json_generator())

        classifier = CorruptionClassifier(
            runner=runner,
            session_service=mock_session_service,
        )

        # When/Then: Raises validation error
        with pytest.raises(Exception):  # JSONDecodeError or ValidationError
            await classifier.classify(sample_corruption_article)

    async def test_classify_raises_on_missing_required_fields(
        self, sample_corruption_article: ClassificationInput, mock_session_service: AsyncMock
    ):
        # Given: Runner returning JSON without required fields
        incomplete_event = Mock()
        incomplete_event.is_final_response = Mock(return_value=True)
        incomplete_event.content = Mock()
        incomplete_event.content.parts = [Mock(text='{"is_relevant": true}')]

        runner = AsyncMock()

        async def incomplete_generator():
            yield incomplete_event

        runner.run_async = Mock(side_effect=lambda **kwargs: incomplete_generator())

        classifier = CorruptionClassifier(
            runner=runner,
            session_service=mock_session_service,
        )

        # When/Then: Raises ValidationError
        with pytest.raises(Exception):  # Pydantic ValidationError
            await classifier.classify(sample_corruption_article)


class TestCorruptionAdapterErrorHandling:
    """Test error scenarios and edge cases."""

    async def test_classify_handles_session_creation_failure(
        self, sample_corruption_article: ClassificationInput, mock_runner: AsyncMock
    ):
        # Given: Session service that raises exception
        failing_service = AsyncMock()
        failing_service.create_session = AsyncMock(
            side_effect=Exception("Session creation failed")
        )

        classifier = CorruptionClassifier(
            runner=mock_runner,
            session_service=failing_service,
        )

        # When/Then: Exception propagates
        with pytest.raises(Exception, match="Session creation failed"):
            await classifier.classify(sample_corruption_article)

    async def test_classify_handles_runner_exception(
        self, sample_corruption_article: ClassificationInput, mock_session_service: AsyncMock
    ):
        # Given: Runner that raises exception
        failing_runner = AsyncMock()

        async def failing_generator():
            raise Exception("Runner failed")
            yield  # Never reached

        failing_runner.run_async = Mock(side_effect=lambda **kwargs: failing_generator())

        classifier = CorruptionClassifier(
            runner=failing_runner,
            session_service=mock_session_service,
        )

        # When/Then: Exception propagates
        with pytest.raises(Exception, match="Runner failed"):
            await classifier.classify(sample_corruption_article)

    async def test_call_agent_returns_default_when_no_final_response(
        self, mock_session: Mock
    ):
        # Given: Runner with no final response event
        non_final_event = Mock()
        non_final_event.is_final_response = Mock(return_value=False)

        runner = AsyncMock()

        async def no_final_generator():
            yield non_final_event

        runner.run_async = Mock(side_effect=lambda **kwargs: no_final_generator())

        classifier = CorruptionClassifier(runner=runner)

        # When: Calling agent async
        response = await classifier._call_agent_async(
            "test", runner, mock_session.user_id, mock_session.id
        )

        # Then: Returns default message
        assert "did not produce" in response.lower() or "no" in response.lower()


@pytest.fixture
def mock_session() -> Mock:
    """Mock Google ADK Session."""
    session = Mock()
    session.id = "test-session-123"
    session.user_id = "classifier_corruption"
    return session


@pytest.fixture
def mock_session_service(mock_session: Mock) -> AsyncMock:
    """Mock InMemorySessionService."""
    service = AsyncMock()
    service.create_session = AsyncMock(return_value=mock_session)
    return service


@pytest.fixture
def mock_final_event() -> Mock:
    """Mock final response event with valid JSON and normalized entities."""
    event = Mock()
    event.is_final_response = Mock(return_value=True)
    event.content = Mock()
    event.content.parts = [
        Mock(
            text='{"is_relevant": true, "confidence": 0.9, "reasoning": "OCG investigation", "key_entities": ["ocg", "ministry_of_education"], "classifier_type": "CORRUPTION", "model_name": "gpt-5-nano"}'
        )
    ]
    event.actions = None
    return event


@pytest.fixture
def mock_runner(mock_final_event: Mock) -> AsyncMock:
    """Mock Google ADK Runner."""
    runner = AsyncMock()

    async def async_event_generator():
        yield mock_final_event

    # Use side_effect to return a fresh async generator for each call
    runner.run_async = Mock(side_effect=lambda **kwargs: async_event_generator())
    return runner
