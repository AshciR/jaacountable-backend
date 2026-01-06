"""
Parallel archive discovery using multiple workers.

Demonstrates how to run multiple GleanerArchiveDiscoverer instances
in parallel to discover articles from multiple months simultaneously.

Usage:
    # Discover 3 months (Sep, Oct, Nov 2021) using 3 parallel workers
    uv run python scripts/parallel_archive_discovery.py --year 2021 --start-month 9 --end-month 11 --workers 3

    # Discover 6 months using 4 workers (workers process months sequentially)
    uv run python scripts/parallel_archive_discovery.py --year 2021 --start-month 7 --end-month 12 --workers 4

    # Discover with custom crawl delay (1 second instead of default 2 seconds)
    uv run python scripts/parallel_archive_discovery.py --year 2021 --start-month 9 --end-month 11 --workers 3 --crawl-delay 1.0
"""

import argparse
import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.log_config import configure_logging
from loguru import logger
from src.article_discovery.discoverers.gleaner_archive_discoverer import (
    GleanerArchiveDiscoverer,
)
from src.article_discovery.models import DiscoveredArticle
from src.article_discovery.utils import deduplicate_discovered_articles


async def main():

    load_dotenv()

    """Main entry point."""
    # Create logs directory if it doesn't exist
    Path("logs").mkdir(exist_ok=True)

    # Configure Loguru with date-stamped log file
    trigger_date = datetime.now().strftime("%Y-%m-%d")
    log_file_path = f"logs/gleaner_archive_discovery_{trigger_date}.log"

    # Use centralized logging configuration
    configure_logging(
        enable_file_logging=True,
        log_file_path=log_file_path,
    )

    logger.info(f"Archive discovery logging to: {log_file_path}")

    parser = argparse.ArgumentParser(
        description="Parallel archive discovery from multiple months"
    )
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Year to discover (e.g., 2021)",
    )
    parser.add_argument(
        "--start-month",
        type=int,
        required=True,
        help="Starting month (1-12, inclusive)",
    )
    parser.add_argument(
        "--end-month",
        type=int,
        required=True,
        help="Ending month (1-12, inclusive)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Maximum number of parallel workers (default: 4)",
    )
    parser.add_argument(
        "--crawl-delay",
        type=float,
        default=2.0,
        help="Delay between requests in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--news-source-id",
        type=int,
        default=1,
        help="Database ID of news source (default: 1)",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.start_month < 1 or args.start_month > 12:
        logger.error(f"Invalid start_month: {args.start_month} (must be 1-12)")
        return 1

    if args.end_month < 1 or args.end_month > 12:
        logger.error(f"Invalid end_month: {args.end_month} (must be 1-12)")
        return 1

    if args.start_month > args.end_month:
        logger.error(
            f"start_month ({args.start_month}) must be <= end_month ({args.end_month})"
        )
        return 1

    if args.workers < 1:
        logger.error(f"workers must be >= 1, got: {args.workers}")
        return 1

    if args.crawl_delay < 0:
        logger.error(f"crawl_delay must be >= 0, got: {args.crawl_delay}")
        return 1

    # Run parallel discovery
    try:
        start_time = time.time()
        articles = await parallel_discovery(
            year=args.year,
            start_month=args.start_month,
            end_month=args.end_month,
            news_source_id=args.news_source_id,
            max_workers=args.workers,
            crawl_delay=args.crawl_delay,
        )
        end_time = time.time()
        elapsed_time = end_time - start_time

        # Display summary
        logger.info("=" * 70)
        logger.info("Discovery Summary:")
        logger.info(f"  Total unique articles: {len(articles)}")
        logger.info(
            f"  Date range: {args.year}-{args.start_month:02d} to {args.year}-{args.end_month:02d}"
        )
        logger.info(f"  Workers used: {args.workers}")
        logger.info(f"  Crawl delay: {args.crawl_delay}s")
        logger.info(f"  Time elapsed: {elapsed_time:.2f}s ({elapsed_time/60:.2f}m)")

        # Per-section breakdown
        sections = {}
        for article in articles:
            sections[article.section] = sections.get(article.section, 0) + 1

        logger.info("  Articles by section:")
        for section, count in sorted(sections.items()):
            logger.info(f"    {section}: {count}")

        logger.info("=" * 70)

        return 0

    except Exception as e:
        logger.error(f"Parallel discovery failed: {e}", exc_info=True)
        return 1


async def parallel_discovery(
    year: int,
    start_month: int,
    end_month: int,
    news_source_id: int,
    max_workers: int = 4,
    crawl_delay: float = 2.0,
) -> list[DiscoveredArticle]:
    """
    Discover articles from multiple months in parallel.

    Args:
        year: Year to discover
        start_month: Starting month (1-12, inclusive)
        end_month: Ending month (1-12, inclusive)
        news_source_id: Database ID of news source
        max_workers: Maximum number of parallel workers (default: 4)
        crawl_delay: Delay between requests in seconds (default: 2.0)

    Returns:
        Deduplicated list of articles from all months
    """
    # Generate list of months to discover
    months = list(range(start_month, end_month + 1))

    logger.info(
        f"Starting parallel discovery: {len(months)} months "
        f"({year}-{start_month:02d} to {year}-{end_month:02d}), "
        f"{max_workers} workers, {crawl_delay}s crawl delay"
    )

    # Create tasks for each month
    tasks = [
        discover_month(year, month, news_source_id, crawl_delay) for month in months
    ]

    # Run tasks in parallel with concurrency limit
    # asyncio.Semaphore limits concurrent workers
    semaphore = asyncio.Semaphore(max_workers)

    async def bounded_task(task):
        async with semaphore:
            return await task

    # Execute all tasks with bounded concurrency
    results = await asyncio.gather(
        *[bounded_task(task) for task in tasks],
        return_exceptions=False,  # Fail-soft already handled in discover_month
    )

    # Combine results from all workers
    all_articles = []
    for month_articles in results:
        all_articles.extend(month_articles)

    logger.info(
        f"All workers completed: {len(all_articles)} total articles "
        f"(before deduplication)"
    )

    # Deduplicate across all months
    deduplicated = deduplicate_discovered_articles(all_articles)

    logger.info(
        f"Deduplication complete: {len(deduplicated)} unique articles "
        f"({len(all_articles) - len(deduplicated)} duplicates removed)"
    )

    return deduplicated


async def discover_month(
    year: int, month: int, news_source_id: int, crawl_delay: float = 2.0
) -> list[DiscoveredArticle]:
    """
    Discover articles for a single month.

    Args:
        year: Year to discover
        month: Month to discover (1-12)
        news_source_id: Database ID of news source
        crawl_delay: Delay between requests in seconds (default: 2.0)

    Returns:
        List of discovered articles for this month
    """
    logger.info(f"Worker started: {year}-{month:02d}")

    try:
        # Create discoverer for this month
        discoverer = GleanerArchiveDiscoverer.for_month(
            year=year,
            month=month,
            crawl_delay=crawl_delay,
        )

        # Discover articles
        articles = await discoverer.discover(news_source_id=news_source_id)

        logger.info(
            f"Worker completed: {year}-{month:02d} "
            f"({len(articles)} articles discovered)"
        )

        return articles

    except Exception as e:
        logger.error(f"Worker failed: {year}-{month:02d} - {e}", exc_info=True)
        # Return empty list on failure (fail-soft)
        return []


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
