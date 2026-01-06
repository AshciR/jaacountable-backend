"""
Simple validation script to test the Phase 3 pipeline integration.

Tests the core workflow: URL → Extract → Classify → Store (if relevant)

Usage:
    python scripts/validate_pipeline.py <article_url>

Example:
    python scripts/validate_pipeline.py "https://jamaica-gleaner.com/article/news/20251201/some-article"
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.database import db_config
from config.log_config import configure_logging
from src.orchestration.service import PipelineOrchestrationService


async def validate_pipeline(url: str, section: str = "news") -> None:
    """
    Validate the Phase 3 pipeline integration.

    Args:
        url: Article URL to process
        section: Article section (default: "news")
    """
    # Initialize orchestration service
    service = PipelineOrchestrationService()

    # Initialize database pool
    await db_config.create_pool()

    try:
        # Process article through pipeline
        # Canonical log line will be emitted by the orchestration service
        async with db_config.connection() as conn:
            result = await service.process_article(
                conn=conn,
                url=url,
                section=section,
                news_source_id=1,  # Jamaica Gleaner
                min_confidence=0.7,
            )

        # Raise exception if there was an error
        if result.error:
            raise Exception(result.error)

    finally:
        await db_config.close_pool()


async def main() -> None:
    """Main entry point."""
    load_dotenv()

    # Create logs directory if it doesn't exist
    Path("logs").mkdir(exist_ok=True)

    # Configure Loguru with date+time stamped log file
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file_path = f"logs/validate_pipeline_{timestamp}.log"

    # Configure logging with file output
    configure_logging(
        enable_file_logging=True,
        log_file_path=log_file_path,
    )

    logger.info(f"Pipeline validation logging to: {log_file_path}")

    if len(sys.argv) < 2:
        print("Usage: python scripts/validate_pipeline.py <article_url>")
        print("\nExample:")
        print('  python scripts/validate_pipeline.py "https://jamaica-gleaner.com/article/news/..."')
        print("\nEnvironment Variables:")
        print("  LOG_JSON=true   Enable JSON structured logging")
        sys.exit(1)

    url = sys.argv[1]
    await validate_pipeline(url)


if __name__ == "__main__":
    asyncio.run(main())
