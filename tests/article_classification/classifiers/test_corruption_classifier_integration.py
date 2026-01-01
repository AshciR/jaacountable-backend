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
from src.article_classification.classifiers.corruption_classifier import (
    CorruptionClassifier,
)


@pytest.fixture
def classifier() -> CorruptionClassifier:
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


@pytest.fixture
def letter_to_editor_article() -> ClassificationInput:
    """Reader letter mentioning corruption - should be NOT RELEVANT."""
    return ClassificationInput(
        url="https://gleaner.newspaperarchive.com/kingston-gleaner/2019-04-05/page-10/",
        title="Reid's resignation disappointing and demoralising",
        section="letters",
        full_text="""
        THE EDITOR, Sir:
        "Mommy, Education Minister Ruel Reid has been fired because of
        nepotism. It is when you hire family and friends without qualification."
        (11-year-old boy, St Elizabeth)

        "Reid was sacked as minister over allegations of corruption and
        misuse of public funds in the ministry." (The Gleaner – March 21, 2019)

        The names of many outstanding Munronians, including Ruel Reid, are
        on the school's honours board. The little boy and other new students
        are likely to learn that it is the same Ruel Reid that was fired because of
        allegations of impropriety in the education ministry.

        Reid's reputation has been damaged. Even if the investigations
        and due process should clear him of any wrongdoing, doubts will
        still linger for many because he has already been tried in the court of
        public opinion.

        DAIVE R FACEY
        DR.Facey@gmail.com
        """,
        published_date=datetime(2019, 4, 5, tzinfo=timezone.utc),
    )


class TestCorruptionClassifierIntegration:
    """Integration tests that make actual LLM API calls."""

    @pytest.mark.external
    @pytest.mark.integration
    async def test_classifies_ocg_investigation_as_relevant(
        self, classifier: CorruptionClassifier, ocg_investigation_article: ClassificationInput
    ):
        # Given: Article about OCG investigation into government contracts
        # When: Classifying the article
        result: ClassificationResult = await classifier.classify(ocg_investigation_article)

        # Then: Article is classified as relevant to corruption
        assert isinstance(result, ClassificationResult)
        assert result.is_relevant is True
        assert result.confidence >= 0.7  # High confidence for clear corruption case
        assert result.classifier_type == ClassifierType.CORRUPTION
        assert result.model_name == "gpt-5-nano"
        assert len(result.reasoning) > 0
        # Should identify OCG as key entity (normalized or raw)
        # The agent may return normalized entities (e.g., "ocg") or raw entities (e.g., "OCG")
        normalized_entities = [entity.lower() for entity in result.key_entities]
        assert any("ocg" in entity or "contractor" in entity for entity in normalized_entities)

    @pytest.mark.external
    @pytest.mark.integration
    async def test_excludes_letter_to_editor_despite_corruption_mention(
        self, classifier: CorruptionClassifier, letter_to_editor_article: ClassificationInput
    ):
        # Given: Letter to the editor that mentions corruption/nepotism
        # When: Classifying the article
        result: ClassificationResult = await classifier.classify(letter_to_editor_article)

        # Then: Article is classified as NOT RELEVANT (editorial content)
        assert isinstance(result, ClassificationResult)
        assert result.is_relevant is False
        assert result.confidence <= 0.3  # Low confidence for editorial content
        assert result.classifier_type == ClassifierType.CORRUPTION
        assert result.model_name == "gpt-5-nano"
        assert len(result.reasoning) > 0
        # Reasoning should mention it's a letter to the editor
        assert any(
            marker in result.reasoning.lower()
            for marker in ["letter", "editor", "opinion", "editorial", "reader"]
        )
