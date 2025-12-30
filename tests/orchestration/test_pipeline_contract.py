"""
Contract test for full pipeline orchestration.

This test validates the complete end-to-end pipeline against live external services
to detect breaking changes in dependencies.
"""
import logging

import asyncpg
import pytest

from src.article_classification.models import ClassifierType
from src.orchestration.service import PipelineOrchestrationService

logger = logging.getLogger(__name__)


class TestPipelineOrchestrationContract:
    """
    Contract test for full pipeline orchestration.

    Validates that the complete pipeline (Extract → Classify → Store) works
    against live external services:
    - Jamaica Gleaner website (live HTTP requests)
    - OpenAI API (real LLM classification calls)
    - PostgreSQL database (test container)

    This test detects breaking changes in:
    - Gleaner website structure
    - OpenAI API changes
    - Pipeline integration issues

    Runs on cron schedule (Monday & Thursday 7 AM UTC) via contract-tests.yml workflow.
    """

    @pytest.mark.external
    @pytest.mark.contract
    async def test_full_pipeline_with_live_gleaner_article(
        self,
        db_connection: asyncpg.Connection,
    ):
        """
        Verify full pipeline works with live Gleaner article.

        This test:
        1. Fetches a real article from Jamaica Gleaner website
        2. Extracts content using real extraction service
        3. Classifies content using real OpenAI API
        4. Stores article in test database

        Detects breaking changes in external dependencies.
        """
        # Given: Live Gleaner article about Petrojam scandal (corruption)
        url = "https://jamaica-gleaner.com/article/lead-stories/20200701/holness-headache-petrojam-scandal-resurfaces-force-wheatley-labelled"
        section = "lead-stories"

        print("\n" + "=" * 80)
        print("CONTRACT TEST: Full Pipeline Validation")
        print("=" * 80)
        print(f"URL: {url}")
        print(f"Section: {section}")

        # Use real services (no mocking)
        service = PipelineOrchestrationService(
            # extraction_service defaults to DefaultArticleExtractionService (real HTTP)
            # classification_service defaults to ClassificationService (real LLM)
            # persistence_service defaults to PostgresArticlePersistenceService (real DB)
        )

        # When: Processing through full pipeline
        print("Processing article through full pipeline...")
        result = await service.process_article(
            conn=db_connection,
            url=url,
            section=section,
            news_source_id=1,  # Jamaica Gleaner
            min_confidence=0.7,
        )

        # Then: Extraction validation
        print("-" * 80)
        print("EXTRACTION RESULTS:")
        print(f"  Extracted: {result.extracted}")
        if not result.extracted:
            print(f"  ✗ Error: {result.error}")
            pytest.fail(
                f"Extraction failed: {result.error}. "
                "Gleaner website structure may have changed."
            )
        print("  ✓ Extraction successful")

        # Classification validation
        print("-" * 80)
        print("CLASSIFICATION RESULTS:")
        print(f"  Classified: {result.classified}")
        if not result.classified:
            print(f"  ✗ Error: {result.error}")
            pytest.fail(
                f"Classification failed: {result.error}. "
                "OpenAI API may be down or model unavailable."
            )

        assert result.classified is True, "Article should be classified via OpenAI API"
        assert len(result.classification_results) >= 1, "Should have classification results"

        # Verify CORRUPTION classification
        corruption_result = next(
            (r for r in result.classification_results
             if r.classifier_type == ClassifierType.CORRUPTION),
            None,
        )
        assert corruption_result is not None, "Should have CORRUPTION classification"

        # Log classification details
        print(f"  Classifier Type: CORRUPTION")
        print(f"  Is Relevant: {corruption_result.is_relevant}")
        print(f"  Confidence: {corruption_result.confidence:.2f}")
        print(f"  Reasoning: {corruption_result.reasoning[:150]}...")
        print(f"  Key Entities: {corruption_result.key_entities}")

        assert corruption_result.is_relevant is True, "Should be marked relevant"
        assert corruption_result.confidence >= 0.7, "Should meet confidence threshold"
        assert len(corruption_result.key_entities) > 0, "Should extract entities"
        print("  ✓ Classification successful (relevant)")

        # Relevance check with helpful error message
        if not result.relevant:
            pytest.fail(
                "Article was not classified as relevant. "
                "This is unexpected for the Petrojam scandal corruption article. "
                "Classification model behavior may have changed."
            )

        # Storage validation
        print("-" * 80)
        print("STORAGE RESULTS:")
        print(f"  Stored: {result.stored}")
        print(f"  Article ID: {result.article_id}")
        print(f"  Classifications Stored: {result.classification_count}")

        assert result.stored is True, "Article should be stored in database"
        assert result.article_id is not None, "Article ID should be assigned"
        assert result.classification_count >= 1, "Classification should be stored"
        assert result.error is None, "No error should occur"
        print("  ✓ Storage successful")

        # Database validation - verify article was actually stored
        article = await _fetch_article_from_db(db_connection, url)
        assert article is not None, "Article should exist in database"
        assert article["url"] == url
        assert article["section"] == "lead-stories"
        assert len(article["title"]) > 0, "Title should not be empty"
        assert len(article["full_text"]) >= 50, "Full text should have substantial content"

        # Entity validation - verify entities were normalized and stored
        entities = await _fetch_article_entities(db_connection, result.article_id)
        assert len(entities) > 0, "Should have stored entities"
        print(f"  Entities Stored: {len(entities)}")

        print("=" * 80)
        print("CONTRACT TEST PASSED: ✓ All pipeline stages validated successfully")
        print("=" * 80 + "\n")

async def _fetch_article_entities(conn: asyncpg.Connection, article_id: int) -> list[asyncpg.Record]:
    """
    Fetch entities associated with an article.

    Args:
        conn: Database connection
        article_id: Article ID

    Returns:
        List of entity records with name and normalized_name
    """
    return await conn.fetch(
        """
        SELECT e.name, e.normalized_name
        FROM entities e
        JOIN article_entities ae ON e.id = ae.entity_id
        WHERE ae.article_id = $1
        """,
        article_id,
    )

async def _fetch_article_from_db(conn: asyncpg.Connection, url: str) -> asyncpg.Record | None:
    """
    Fetch article from database by URL.

    Args:
        conn: Database connection
        url: Article URL

    Returns:
        Article record or None if not found
    """
    return await conn.fetchrow(
        "SELECT id, url, title, section, full_text FROM articles WHERE url = $1",
        url,
    )