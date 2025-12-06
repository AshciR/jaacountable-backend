"""Integration tests for CorruptionClassifierAdapter.

These tests make actual LLM API calls and verify the classifier works end-to-end.
Run sparingly to avoid API costs.
"""
import pytest
from datetime import datetime, timezone

from src.article_classification.models import (
    ClassificationInput,
    ClassificationResult,
    ClassifierType,
)
from src.article_classification.agents.corruption_classifier import (
    CorruptionClassifier,
)


@pytest.fixture
def adapter() -> CorruptionClassifier:
    """Create real adapter instance (makes actual LLM calls)."""
    return CorruptionClassifier()


@pytest.fixture
def ocg_investigation_article() -> ClassificationInput:
    """Article about OCG investigation - should be RELEVANT."""
    return ClassificationInput(
        url="https://jamaica-gleaner.com/article/news/ocg-investigation",
        title="OCG Launches Probe into Education Ministry Contract Irregularities",
        section="news",
        full_text="""
        The Office of the Contractor General (OCG) has launched an investigation into
        alleged contract irregularities at the Ministry of Education involving $50 million
        in procurement contracts. The probe was initiated following complaints about the
        procurement process for school furniture and equipment. Officials from the OCG
        stated that they will be examining all documentation related to the contracts
        and interviewing relevant ministry staff.
        """,
        published_date=datetime.now(timezone.utc),
    )


class TestCorruptionClassifierIntegration:
    """Integration tests that make actual LLM API calls."""

    @pytest.mark.integration
    async def test_classifies_ocg_investigation_as_relevant(
        self, adapter: CorruptionClassifier, ocg_investigation_article: ClassificationInput
    ):
        # Given: Article about OCG investigation into government contracts
        # When: Classifying the article
        result = await adapter.classify(ocg_investigation_article)

        # Then: Article is classified as relevant to corruption
        assert isinstance(result, ClassificationResult)
        assert result.is_relevant is True
        assert result.confidence >= 0.7  # High confidence for clear corruption case
        assert result.classifier_type == ClassifierType.CORRUPTION
        assert result.model_name == "gpt-5-nano"
        assert len(result.reasoning) > 0
        # Should identify OCG as key entity
        assert any("OCG" in entity or "Contractor General" in entity for entity in result.key_entities)
