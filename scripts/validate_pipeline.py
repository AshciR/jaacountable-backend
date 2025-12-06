"""
Simple validation script to test the Phase 3 pipeline integration.

Tests the core workflow: URL → Extract → Classify → Store (if relevant)

Usage:
    python scripts/validate_pipeline.py <article_url>

Example:
    python scripts/validate_pipeline.py "https://jamaica-gleaner.com/article/news/20251201/some-article"
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.database import db_config
from src.article_extractor.service import ArticleExtractionService
from src.article_classification.service import ClassificationService
from src.article_classification.agents.corruption_classifier import CorruptionClassifier
from src.article_persistence.service import store_article_with_classifications
from src.orchestration.converters import (
    extracted_content_to_classification_input,
    filter_relevant_classifications,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def validate_pipeline(url: str, section: str = "news") -> None:
    """
    Validate the Phase 3 pipeline integration.

    Args:
        url: Article URL to process
        section: Article section (default: "news")
    """
    logger.info(f"Starting pipeline validation for URL: {url}")

    # Initialize services
    extraction_service = ArticleExtractionService()
    classification_service = ClassificationService(
        classifiers=[
            CorruptionClassifier(),
        ]
    )

    try:
        # Step 1: Extract article content
        logger.info("Step 1: Extracting article content...")
        extracted = extraction_service.extract_article_content(url)
        logger.info(f"  ✓ Extracted: {extracted.title[:100]}...")
        logger.info(f"  ✓ Full text length: {len(extracted.full_text)} characters")

        # Step 2: Convert to classification input
        logger.info("Step 2: Converting to classification input...")
        classification_input = extracted_content_to_classification_input(
            extracted=extracted,
            url=url,
            section=section,
        )
        logger.info(f"  ✓ Classification input ready")

        # Step 3: Classify article
        logger.info("Step 3: Classifying article...")
        classification_results = await classification_service.classify(
            classification_input
        )
        logger.info(f"  ✓ Received {len(classification_results)} classification results")

        for i, result in enumerate(classification_results, 1):
            logger.info(
                f"    - Classifier {i} ({result.classifier_type.value}): "
                f"relevant={result.is_relevant}, confidence={result.confidence:.2f}"
            )
            if result.reasoning:
                logger.info(f"      Reasoning: {result.reasoning[:200]}...")

        # Step 4: Filter relevant classifications
        logger.info("Step 4: Filtering relevant classifications (min confidence: 0.7)...")
        relevant_results = filter_relevant_classifications(
            results=classification_results,
            min_confidence=0.7,
        )

        if not relevant_results:
            logger.info("  ✗ Article is NOT relevant (skipping storage)")
            logger.info("\n=== VALIDATION COMPLETE ===")
            logger.info("Article was not stored (below relevance threshold)")
            return

        logger.info(f"  ✓ Article IS relevant ({len(relevant_results)} classifiers passed)")

        # Step 5: Store article and classifications
        logger.info("Step 5: Storing article and classifications in database...")

        # Initialize database pool
        await db_config.create_pool()

        try:
            # Store article with classifications
            result = await store_article_with_classifications(
                db_config=db_config,
                extracted=extracted,
                url=url,
                section=section,
                relevant_classifications=relevant_results,
                news_source_id=1,  # Jamaica Gleaner
            )

            if result["stored"]:
                logger.info(f"  ✓ Article stored with ID: {result['article_id']}")
                logger.info(f"  ✓ Stored {result['classification_count']} classifications")

                logger.info("\n=== VALIDATION COMPLETE ===")
                logger.info(f"Article ID: {result['article_id']}")
                logger.info(f"Title: {result['article'].title}")
                logger.info(f"Relevant classifications: {result['classification_count']}")
                logger.info("✓ Pipeline integration successful!")
            else:
                logger.info("  ⚠ Article already exists in database (duplicate URL)")
                logger.info("\n=== VALIDATION COMPLETE ===")
                logger.info("Article was not stored (duplicate)")

        finally:
            await db_config.close_pool()

    except Exception as e:
        logger.error(f"Pipeline validation failed: {e}", exc_info=True)
        raise


async def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/validate_pipeline.py <article_url>")
        print("\nExample:")
        print('  python scripts/validate_pipeline.py "https://jamaica-gleaner.com/article/news/..."')
        sys.exit(1)

    url = sys.argv[1]
    await validate_pipeline(url)


if __name__ == "__main__":
    asyncio.run(main())
