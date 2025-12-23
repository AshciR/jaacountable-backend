"""Integration tests for entity normalization agent.

These tests make actual LLM API calls to verify the normalization agent works correctly.
Run sparingly to avoid API costs.
"""
import pytest

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, Session
from google.genai import types
from google.genai.types import Content

from src.article_classification.agents.normalization_agent import normalization_agent
from src.article_classification.models import (
    EntityNormalizationInput,
    EntityNormalizationResult,
)
from src.article_classification.base import APP_NAME, NORMALIZATION_MODEL


@pytest.fixture
def session_service() -> InMemorySessionService:
    """Create session service for agent."""
    return InMemorySessionService()


@pytest.fixture
async def session(session_service: InMemorySessionService) -> Session:
    """Create test session."""
    return await session_service.create_session(
        app_name=APP_NAME,
        user_id="test_normalization"
    )


@pytest.fixture
def runner(session_service: InMemorySessionService) -> Runner:
    """Create runner with normalization agent."""
    return Runner(
        app_name=APP_NAME,
        agent=normalization_agent,
        session_service=session_service
    )


def build_normalization_query(entity_names: list[str], context: str = "") -> str:
    """
    Build a normalization query string for the agent.

    Args:
        entity_names: List of entity names to normalize
        context: Optional context about the entities

    Returns:
        Formatted query string
    """
    context_line = f"Context: {context}\n" if context else ""
    return f"""Please normalize these entity names:

Entity names: {entity_names}
{context_line}
Return the normalization as JSON."""


async def call_agent_async(query: str, runner: Runner, user_id: str, session_id: str) -> str:
    """
    Call the normalization agent and extract final response.

    This is similar to the _call_agent_async pattern used in corruption_classifier.
    """
    content: Content = types.Content(
        role='user',
        parts=[types.Part(text=query)]
    )

    final_response_text = "Agent did not produce a final response."

    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
        if event.is_final_response():
            if event.content and event.content.parts:
                final_response_text = event.content.parts[0].text
            elif event.actions and event.actions.escalate:
                final_response_text = f"Agent escalated: {event.error_message or 'No specific message.'}"
            break

    return final_response_text


@pytest.mark.external
@pytest.mark.integration
class TestNormalizationAgentIntegration:
    """Integration tests with actual LLM API calls."""

    async def test_normalize_jamaican_official_with_title(
        self, runner: Runner, session: Session
    ):
        # Given: Query with entity to normalize
        query = build_normalization_query(
            entity_names=["Hon. Ruel Reid"],
            context="corruption investigation"
        )

        # When: Normalizing via agent
        response = await call_agent_async(query, runner, session.user_id, session.id)

        # Then: Returns normalized entity with underscores
        result = EntityNormalizationResult.model_validate_json(response)
        assert isinstance(result, EntityNormalizationResult)
        assert "Hon. Ruel Reid" in result.normalized_entities
        normalized = result.normalized_entities["Hon. Ruel Reid"]
        # Should remove title, lowercase, and use underscores
        assert "ruel_reid" == normalized
        assert result.confidence >= 0.8  # Should be confident
        assert result.model_name == NORMALIZATION_MODEL

    async def test_normalize_acronym(
        self, runner: Runner, session: Session
    ):
        # Given: Query with acronym
        query = build_normalization_query(
            entity_names=["OCG"],
            context="government investigation"
        )

        # When: Normalizing via agent
        response = await call_agent_async(query, runner, session.user_id, session.id)

        # Then: Returns acronym in lowercase
        result = EntityNormalizationResult.model_validate_json(response)
        assert "OCG" in result.normalized_entities
        assert result.normalized_entities["OCG"] == "ocg"
        assert result.confidence >= 0.9  # Very confident for acronyms
        assert result.model_name == NORMALIZATION_MODEL

    async def test_normalize_ministry(
        self, runner: Runner, session: Session
    ):
        # Given: Query with ministry name
        query = build_normalization_query(
            entity_names=["Ministry of Education"],
            context="government entity"
        )

        # When: Normalizing via agent
        response = await call_agent_async(query, runner, session.user_id, session.id)

        # Then: Returns standardized ministry name with underscores
        result = EntityNormalizationResult.model_validate_json(response)
        assert "Ministry of Education" in result.normalized_entities
        normalized = result.normalized_entities["Ministry of Education"]
        assert normalized == "ministry_of_education"
        assert result.confidence >= 0.8
        assert result.model_name == NORMALIZATION_MODEL

    async def test_normalize_multiple_entities(
        self, runner: Runner, session: Session
    ):
        # Given: Query with multiple entities
        query = build_normalization_query(
            entity_names=["Hon. Ruel Reid", "OCG", "Ministry of Education", "The OCG"],
            context="corruption investigation involving government officials"
        )

        # When: Normalizing via agent
        response = await call_agent_async(query, runner, session.user_id, session.id)

        # Then: All entities normalized correctly
        result = EntityNormalizationResult.model_validate_json(response)
        assert len(result.normalized_entities) == 4

        # Check individual normalizations
        assert result.normalized_entities["Hon. Ruel Reid"] == "ruel_reid"
        assert result.normalized_entities["OCG"] == "ocg"
        assert result.normalized_entities["Ministry of Education"] == "ministry_of_education"
        assert result.normalized_entities["The OCG"] == "ocg"  # Should handle "The" prefix

        assert result.confidence >= 0.7  # Overall confidence should be good
        assert len(result.notes) > 0  # Should provide notes
        assert result.model_name == NORMALIZATION_MODEL

    async def test_normalize_with_various_titles(
        self, runner: Runner, session: Session
    ):
        # Given: Query with various title variations
        query = build_normalization_query(
            entity_names=["Mr. Andrew Holness", "Dr. Nigel Clarke", "Education Minister Reid", "Prime Minister Holness"]
        )

        # When: Normalizing via agent
        response = await call_agent_async(query, runner, session.user_id, session.id)

        # Then: All titles removed, names normalized with underscores
        result = EntityNormalizationResult.model_validate_json(response)

        # All should be lowercase with underscores, titles removed
        assert "andrew_holness" in result.normalized_entities["Mr. Andrew Holness"]
        assert "nigel_clarke" in result.normalized_entities["Dr. Nigel Clarke"]
        assert "reid" in result.normalized_entities["Education Minister Reid"]
        assert "holness" in result.normalized_entities["Prime Minister Holness"]

        assert result.confidence >= 0.8
        assert result.model_name == NORMALIZATION_MODEL
