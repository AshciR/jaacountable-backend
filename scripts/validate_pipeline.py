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
from src.orchestration.service import PipelineOrchestrationService
from src.orchestration.models import OrchestrationResult


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

    # Initialize orchestration service
    service = PipelineOrchestrationService()

    # Initialize database pool
    await db_config.create_pool()

    try:
        # Process article through pipeline
        async with db_config.connection() as conn:
            result = await service.process_article(
                conn=conn,
                url=url,
                section=section,
                news_source_id=1,  # Jamaica Gleaner
                min_confidence=0.7,
            )

        # Log results based on OrchestrationResult
        _log_pipeline_result(result)

        # Raise exception if there was an error
        if result.error:
            raise Exception(result.error)

    finally:
        await db_config.close_pool()


def _log_pipeline_result(result: OrchestrationResult) -> None:
    """Log the pipeline processing result."""

    if result.error:
        logger.error(f"Pipeline failed: {result.error}")
        return

    # Log extraction
    if result.extracted:
        logger.info("✓ Article extracted successfully")

    # Log classification
    if result.classified:
        logger.info(f"✓ Article classified ({len(result.classification_results)} results)")
        for cr in result.classification_results:
            logger.info(
                f"  - {cr.classifier_type.value}: "
                f"relevant={cr.is_relevant}, confidence={cr.confidence:.2f}"
            )

    # Log relevance
    if result.relevant:
        logger.info(f"✓ Article is relevant ({result.classification_count} classifiers passed)")
    else:
        logger.info("✗ Article is NOT relevant (skipping storage)")

    # Log storage
    if result.stored:
        logger.info(f"✓ Article stored with ID: {result.article_id}")
        logger.info(f"✓ Stored {result.classification_count} classifications")
        logger.info("\n=== VALIDATION COMPLETE ===")
        logger.info("✓ Pipeline integration successful!")
    elif result.relevant and not result.stored:
        logger.info("⚠ Article already exists in database (duplicate URL)")
        logger.info("\n=== VALIDATION COMPLETE ===")
        logger.info("Article was not stored (duplicate)")
    else:
        logger.info("\n=== VALIDATION COMPLETE ===")
        logger.info("Article was not stored (below relevance threshold)")


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
