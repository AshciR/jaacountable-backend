"""Service for normalizing entity names using the normalization agent."""
import json
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, Session, BaseSessionService
from google.genai import types
from google.genai.types import Content

from src.article_classification.agents.normalization_agent import normalization_agent
from src.article_classification.models import NormalizedEntity
from src.article_classification.base import APP_NAME


class EntityNormalizerService:
    """Wraps normalization_agent and implements EntityNormalizer protocol."""

    agent: LlmAgent
    session_service: BaseSessionService
    runner: Runner

    def __init__(
        self,
        agent: LlmAgent | None = None,
        session_service: BaseSessionService | None = None,
        runner: Runner | None = None,
    ):
        """
        Initialize the normalizer service.

        Args:
            agent: LLM agent (defaults to normalization_agent)
            session_service: Session service (defaults to InMemorySessionService)
            runner: Pre-configured runner (defaults to new Runner with agent+service)
        """
        self.agent = agent or normalization_agent
        self.session_service = session_service or InMemorySessionService()
        self.runner = runner or Runner(
            app_name=APP_NAME,
            agent=self.agent,
            session_service=self.session_service
        )

    async def normalize(self, entities: list[str]) -> list[NormalizedEntity]:
        """Normalize a batch of entities using the normalization agent."""
        if not entities:
            raise ValueError("entities list cannot be empty")

        # Create new session for this normalization
        session: Session = await self.session_service.create_session(
            app_name=APP_NAME,
            user_id="entity_normalizer"
        )

        # Build prompt for normalization agent
        entities_str = ", ".join(f'"{e}"' for e in entities)
        prompt = f"Normalize these entities: {entities_str}"

        # Call normalization agent using runner
        response = await self._call_agent_async(prompt, session.user_id, session.id)

        # Parse JSON response
        result = json.loads(response)

        # Convert to NormalizedEntity objects
        normalized = []
        for item in result["normalized_entities"]:
            normalized.append(NormalizedEntity(
                original_value=item["original_value"],
                normalized_value=item["normalized_value"],
                confidence=item["confidence"],
                reason=item["reason"],
                context=""  # Not used currently
            ))

        return normalized

    async def _call_agent_async(self, query: str, user_id: str, session_id: str) -> str:
        """Call the normalization agent and return the final response."""
        # Prepare the user's message in ADK format
        content: Content = types.Content(
            role='user',
            parts=[types.Part(text=query)]
        )

        final_response_text = "Agent did not produce a final response."

        # Execute the agent and iterate through events
        async for event in self.runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content
        ):
            if event.is_final_response():
                if event.content and event.content.parts:
                    final_response_text = event.content.parts[0].text
                elif event.actions and event.actions.escalate:
                    final_response_text = f"Agent escalated: {event.error_message or 'No specific message.'}"
                break

        return final_response_text
