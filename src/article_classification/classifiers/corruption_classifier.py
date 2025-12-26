"""Adapter for corruption classifier agent to implement ArticleClassifier Protocol."""

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, Session, BaseSessionService
from google.genai import types
from google.genai.types import Content

from src.article_classification.models import (
    ClassificationInput,
    ClassificationResult,
)
from src.article_classification.agents.corruption_agent import corruption_classifier
from src.article_classification.base import APP_NAME


class CorruptionClassifier:
    """
    Adapter that wraps the Google ADK corruption classifier agent
    to implement the ArticleClassifier Protocol.

    This adapter:
    1. Converts ClassificationInput to ADK session format
    2. Executes the LlmAgent via ADK Runner (reused for efficiency)
    3. Parses LLM JSON output to ClassificationResult
    4. Satisfies ArticleClassifier Protocol through structural subtyping

    Design: Runner is created once and reused for all classifications.
    Each classify() call creates a new session (isolated by session_id).
    """
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
        Initialize the adapter with corruption classifier agent.

        Creates Runner and SessionService once for reuse across all
        classify() calls. This is more efficient than creating new
        Runner instances for each classification.

        Args:
            agent: LLM agent (defaults to corruption_classifier)
            session_service: Session service (defaults to InMemorySessionService)
            runner: Pre-configured runner (defaults to new Runner with agent+service)
                   If provided, agent and session_service are ignored.
        """
        self.agent = agent or corruption_classifier
        self.session_service = session_service or InMemorySessionService()
        self.runner = runner or Runner(
            app_name=APP_NAME,
            agent=self.agent,
            session_service=self.session_service
        )

    async def classify(
        self, article: ClassificationInput
    ) -> ClassificationResult:
        """
        Classify article using corruption classifier agent.

        Creates a new session for this classification (isolated by session_id),
        then reuses the Runner to execute the agent.

        Args:
            article: Article data with url, title, section, full_text, published_date

        Returns:
            ClassificationResult with is_relevant (true/false), confidence,
            reasoning, key_entities, classifier_type=CORRUPTION, and model_name

        Raises:
            ValueError: If article data is invalid or LLM returns invalid JSON
        """
        # Create new session for this classification
        session: Session = await self.session_service.create_session(
            app_name=APP_NAME,
            user_id="classifier_corruption"
        )

        # Build prompt with article data
        prompt: str = self._build_prompt(article)

        # Classify using the LLM
        response: str = await self._call_agent_async(prompt, self.runner, session.user_id, session.id)

        # Parse JSON response to ClassificationResult
        result: ClassificationResult = ClassificationResult.model_validate_json(response)

        return result

    def _build_prompt(self, article: ClassificationInput) -> str:
        """Build prompt with article data for LLM agent."""
        return f"""Analyze this Jamaican news article for corruption and government accountability issues:

**Article Details:**
- Title: {article.title}
- URL: {article.url}
- Section: {article.section}
- Published: {article.published_date or 'Unknown'}

**Full Text:**
{article.full_text}

Please analyze this article and return your classification as valid JSON matching the ClassificationResult schema."""

    async def _call_agent_async(self, query: str, runner: Runner, user_id: str, session_id: str) -> str:
        """Sends a query to the agent and prints the final response."""

        # Prepare the user's message in ADK format
        content: Content = types.Content(
            role='user',
            parts=[types.Part(text=query)]
        )

        final_response_text = "Agent did not produce a final response."  # Default

        # Key Concept: run_async executes the agent logic and yields Events.
        # We iterate through events to find the final answer.
        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
            # You can uncomment the line below to see *all* events during execution
            # print(f"  [Event] Author: {event.author}, Type: {type(event).__name__}, Final: {event.is_final_response()}, Content: {event.content}")

            # Key Concept: is_final_response() marks the concluding message for the turn.
            if event.is_final_response():
                if event.content and event.content.parts:
                    # Assuming text response in the first part
                    final_response_text = event.content.parts[0].text
                elif event.actions and event.actions.escalate:  # Handle potential errors/escalations
                    final_response_text = f"Agent escalated: {event.error_message or 'No specific message.'}"
                # Add more checks here if needed (e.g., specific error codes)
                break  # Stop processing events once the final response is found

        return final_response_text


