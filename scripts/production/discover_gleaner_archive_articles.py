"""
Production archive discovery script with JSONL export.

Discovers articles from Jamaica Gleaner archives using parallel workers
and exports results to JSONL format for pipeline ingestion.

Usage:
    # Discover 3 months (Sep, Oct, Nov 2021) using 3 parallel workers
    uv run python scripts/production/discover_articles.py --year 2021 --start-month 9 --end-month 11 --workers 3

    # Discover 6 months using 4 workers (workers process months sequentially)
    uv run python scripts/production/discover_articles.py --year 2021 --start-month 7 --end-month 12 --workers 4

    # Discover with custom crawl delay and output directory
    uv run python scripts/production/discover_articles.py \
        --year 2021 --start-month 9 --end-month 11 \
        --workers 3 --crawl-delay 0.5 \
        --output-dir /path/to/output

Output:
    - Success file: {output_dir}/gleaner_archive_{year}_{start_month}-{end_month}.jsonl
    - Failures file: {output_dir}/gleaner_archive_{year}_{start_month}-{end_month}-failures.jsonl
    - Log file: {output_dir}/gleaner_archive_production_{timestamp}.log
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.log_config import configure_logging
from src.article_discovery.discoverers.gleaner_archive_discoverer import (
    GleanerArchiveDiscoverer,
)
from src.article_discovery.models import DiscoveredArticle
from src.article_discovery.utils import deduplicate_discovered_articles


@dataclass
class MonthDiscoveryResult:
    """
    Result from discovering a single month.

    Tracks both successful discoveries and failures, with stub articles
    created for failed months to enable retry tracking.

    Attributes:
        year: Year that was discovered
        month: Month that was discovered (1-12)
        articles: Discovered articles (may be stub articles for failures)
        success: Whether discovery succeeded
        error: Error message if discovery failed
    """

    year: int
    month: int
    articles: list[DiscoveredArticle]
    success: bool
    error: str | None = None


async def parallel_discovery_with_tracking(
    year: int,
    start_month: int,
    end_month: int,
    news_source_id: int,
    max_workers: int = 4,
    crawl_delay: float = 0.5,
) -> dict[str, list[DiscoveredArticle]]:
    """
    Discover articles from multiple months in parallel with failure tracking.

    Args:
        year: Year to discover
        start_month: Starting month (1-12, inclusive)
        end_month: Ending month (1-12, inclusive)
        news_source_id: Database ID of news source
        max_workers: Maximum number of parallel workers (default: 4)
        crawl_delay: Delay between requests in seconds (default: 0.5)

    Returns:
        Dictionary with 'success' and 'failures' keys containing article lists
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
        discover_month_with_tracking(year, month, news_source_id, crawl_delay)
        for month in months
    ]

    # Run tasks in parallel with concurrency limit
    semaphore = asyncio.Semaphore(max_workers)

    async def bounded_task(task):
        async with semaphore:
            return await task

    # Execute all tasks with bounded concurrency
    results = await asyncio.gather(
        *[bounded_task(task) for task in tasks],
        return_exceptions=False,  # Fail-soft already handled in discover_month_with_tracking
    )

    # Separate successful and failed discoveries
    success_articles: list[DiscoveredArticle] = []
    failure_articles: list[DiscoveredArticle] = []
    failed_months: list[tuple[int, int]] = []

    for result in results:
        if result.success:
            success_articles.extend(result.articles)
        else:
            failure_articles.extend(result.articles)
            failed_months.append((result.year, result.month))

    logger.info(
        f"All workers completed: {len(success_articles)} successful articles, "
        f"{len(failure_articles)} failure stubs (before deduplication)"
    )

    if failed_months:
        failed_months_str = ", ".join(
            [f"{y}-{m:02d}" for y, m in failed_months]
        )
        logger.warning(f"Failed months: {failed_months_str}")

    # Deduplicate each group separately
    deduplicated_success = deduplicate_discovered_articles(success_articles)
    deduplicated_failures = deduplicate_discovered_articles(failure_articles)

    logger.info(
        f"Deduplication complete: "
        f"{len(deduplicated_success)} unique successful articles "
        f"({len(success_articles) - len(deduplicated_success)} duplicates removed), "
        f"{len(deduplicated_failures)} unique failure stubs "
        f"({len(failure_articles) - len(deduplicated_failures)} duplicates removed)"
    )

    return {
        "success": deduplicated_success,
        "failures": deduplicated_failures,
    }


async def discover_month_with_tracking(
    year: int, month: int, news_source_id: int, crawl_delay: float = 0.5
) -> MonthDiscoveryResult:
    """
    Discover articles for a single month with success/failure tracking.

    On success, returns discovered articles with success=True.
    On failure, creates stub article with month's base URL for retry tracking.

    Args:
        year: Year to discover
        month: Month to discover (1-12)
        news_source_id: Database ID of news source
        crawl_delay: Delay between requests in seconds (default: 0.5)

    Returns:
        MonthDiscoveryResult with discovered articles or stub article on failure
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

        return MonthDiscoveryResult(
            year=year,
            month=month,
            articles=articles,
            success=True,
            error=None,
        )

    except Exception as e:
        logger.error(f"Worker failed: {year}-{month:02d} - {e}", exc_info=True)

        # Create stub article for failed month to enable retry tracking
        stub_article = DiscoveredArticle(
            url=f"https://gleaner.newspaperarchive.com/kingston-gleaner/{year}-{month:02d}-01/",
            news_source_id=news_source_id,
            section="archive",
            discovered_at=datetime.now(timezone.utc),
            title=f"FAILED: {year}-{month:02d}",
            published_date=datetime(year, month, 1, tzinfo=timezone.utc),
        )

        return MonthDiscoveryResult(
            year=year,
            month=month,
            articles=[stub_article],
            success=False,
            error=str(e),
        )


def write_jsonl(articles: list[DiscoveredArticle], output_path: Path) -> None:
    """
    Write discovered articles to JSONL file.

    Each line in the file is a JSON object representing a DiscoveredArticle.
    Uses Pydantic's model_dump(mode='json') to convert datetime to ISO 8601 format.

    Args:
        articles: List of articles to write
        output_path: Path to output JSONL file

    Raises:
        IOError: If file writing fails
    """
    # Create parent directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write JSONL
    with open(output_path, "w", encoding="utf-8") as f:
        for article in articles:
            # Convert Pydantic model to dict with JSON-serializable values
            article_dict = article.model_dump(mode="json")
            # Write as JSON line (one object per line)
            f.write(json.dumps(article_dict, ensure_ascii=False) + "\n")

    logger.info(f"Wrote {len(articles)} articles to {output_path}")


async def main() -> int:
    """Main entry point."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Production archive discovery with JSONL export"
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
        default=0.5,
        help="Delay between requests in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--news-source-id",
        type=int,
        default=1,
        help="Database ID of news source (default: 1)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="scripts/production/output",
        help="Output directory path (default: scripts/production/output)",
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

    # Setup output directory and logging
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file_path = output_dir / f"gleaner_archive_production_{timestamp}.log"

    # Use centralized logging configuration
    configure_logging(
        enable_file_logging=True,
        log_file_path=str(log_file_path),
    )

    logger.info(f"Archive discovery logging to: {log_file_path}")

    # Run parallel discovery
    try:
        start_time = time.time()
        results: dict[str, list[DiscoveredArticle]] = await parallel_discovery_with_tracking(
            year=args.year,
            start_month=args.start_month,
            end_month=args.end_month,
            news_source_id=args.news_source_id,
            max_workers=args.workers,
            crawl_delay=args.crawl_delay,
        )
        end_time = time.time()
        elapsed_time = end_time - start_time

        # Generate output filenames
        success_filename = (
            f"gleaner_archive_{args.year}_{args.start_month}-{args.end_month}.jsonl"
        )
        failures_filename = f"gleaner_archive_{args.year}_{args.start_month}-{args.end_month}-failures.jsonl"

        success_path = output_dir / success_filename
        failures_path = output_dir / failures_filename

        # Write output files
        write_jsonl(results["success"], success_path)
        write_jsonl(results["failures"], failures_path)

        # Display summary
        logger.info("=" * 70)
        logger.info("Discovery Summary:")
        logger.info(f"  Total successful articles: {len(results['success'])}")
        logger.info(f"  Total failed months: {len(results['failures'])}")
        logger.info(
            f"  Date range: {args.year}-{args.start_month:02d} to {args.year}-{args.end_month:02d}"
        )
        logger.info(f"  Workers used: {args.workers}")
        logger.info(f"  Crawl delay: {args.crawl_delay}s")
        logger.info(f"  Time elapsed: {elapsed_time:.2f}s ({elapsed_time/60:.2f}m)")
        logger.info(f"  Success file: {success_path}")
        logger.info(f"  Failures file: {failures_path}")
        logger.info(f"  Log file: {log_file_path}")

        # Per-section breakdown (success articles only)
        if results["success"]:
            sections = {}
            for article in results["success"]:
                sections[article.section] = sections.get(article.section, 0) + 1

            logger.info("  Successful articles by section:")
            for section, count in sorted(sections.items()):
                logger.info(f"    {section}: {count}")

        logger.info("=" * 70)

        return 0

    except Exception as e:
        logger.error(f"Parallel discovery failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
