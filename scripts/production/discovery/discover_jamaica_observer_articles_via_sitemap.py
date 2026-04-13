"""
Production discovery script for Jamaica Observer articles via sitemaps.

Crawls the Jamaica Observer sitemap index to discover article URLs within
a target date range and exports results to JSONL format for pipeline ingestion.

Usage:
    # Discover 1 year (Jan 2020 → Jan 2021) with default settings
    PYTHONPATH=. uv run python scripts/production/discovery/discover_jamaica_observer_articles_via_sitemap.py \\
        --start-date 2020-01-01 --end-date 2021-01-01

    # Discover with custom delay and output directory
    PYTHONPATH=. uv run python scripts/production/discovery/discover_jamaica_observer_articles_via_sitemap.py \\
        --start-date 2020-01-01 --end-date 2021-01-01 \\
        --delay 2.0 --output-dir /path/to/output

    # Verbose output for debugging
    PYTHONPATH=. uv run python scripts/production/discovery/discover_jamaica_observer_articles_via_sitemap.py \\
        --start-date 2020-01-01 --end-date 2021-01-01 --verbose

Output:
    - Success file: {output_dir}/jamaica_observer_discovery_{start_date}_to_{end_date}_{timestamp}.jsonl
    - Failures file: {output_dir}/jamaica_observer_discovery_{start_date}_to_{end_date}_{timestamp}-failures.jsonl
    - Log file: {output_dir}/jamaica_observer_discovery_{start_date}_to_{end_date}_{timestamp}.log
"""

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from config.log_config import configure_logging
from scripts.production.discovery.utils import build_failure_stubs, write_jsonl
from src.article_discovery.discoverers.jamaica_observer_sitemap_discoverer import (
    JamaicaObserverSitemapDiscoverer,
)


async def main() -> int:
    """Main entry point."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Discover Jamaica Observer articles via sitemaps and export to JSONL"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        required=True,
        help="Start of date range (inclusive), format: YYYY-MM-DD",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        required=True,
        help="End of date range (inclusive), format: YYYY-MM-DD",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Delay between sitemap requests in seconds (default: 1.5)",
    )
    parser.add_argument(
        "--news-source-id",
        type=int,
        default=2,
        help="Database ID of news source (default: 2 = Jamaica Observer)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="scripts/production/discovery/output",
        help="Output directory path (default: scripts/production/discovery/output)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug-level logging",
    )

    args = parser.parse_args()

    # Parse and validate dates
    try:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        print(f"ERROR: Invalid --start-date format: {args.start_date!r} (expected YYYY-MM-DD)")
        return 1

    try:
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        print(f"ERROR: Invalid --end-date format: {args.end_date!r} (expected YYYY-MM-DD)")
        return 1

    if start_date > end_date:
        print(f"ERROR: --start-date ({args.start_date}) must be <= --end-date ({args.end_date})")
        return 1

    if args.delay < 0:
        print(f"ERROR: --delay must be >= 0, got: {args.delay}")
        return 1

    # Setup output directory and logging
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    date_range_str = f"{args.start_date}_to_{args.end_date}"
    log_file_path = output_dir / f"jamaica_observer_discovery_{date_range_str}_{timestamp}.log"

    configure_logging(
        enable_file_logging=True,
        log_file_path=str(log_file_path),
        log_level="DEBUG" if args.verbose else "INFO",
    )

    logger.info(f"Jamaica Observer discovery logging to: {log_file_path}")

    # Generate output filenames
    success_path = output_dir / f"jamaica_observer_discovery_{date_range_str}_{timestamp}.jsonl"
    failures_path = output_dir / f"jamaica_observer_discovery_{date_range_str}_{timestamp}-failures.jsonl"

    # Run discovery
    try:
        start_time = time.time()

        discoverer = JamaicaObserverSitemapDiscoverer(
            start_date=start_date,
            end_date=end_date,
            crawl_delay=args.delay,
        )

        articles = await discoverer.discover(news_source_id=args.news_source_id)
        failure_stubs = build_failure_stubs(
            discoverer.failed_sitemaps,
            args.news_source_id,
            url_builder=lambda s: f"https://www.jamaicaobserver.com/{s}",
            section="archive",
        )

        elapsed = time.time() - start_time

        # Write output files
        write_jsonl(articles, success_path)
        write_jsonl(failure_stubs, failures_path)

        # Summary
        logger.info("=" * 70)
        logger.info("Discovery Summary:")
        logger.info(f"  Total articles discovered: {len(articles)}")
        logger.info(f"  Failed sitemaps: {len(discoverer.failed_sitemaps)}")
        logger.info(f"  Date range: {args.start_date} to {args.end_date}")
        logger.info(f"  Crawl delay: {args.delay}s")
        logger.info(f"  Time elapsed: {elapsed:.2f}s ({elapsed / 60:.2f}m)")
        logger.info(f"  Success file: {success_path}")
        logger.info(f"  Failures file: {failures_path}")
        logger.info(f"  Log file: {log_file_path}")

        if discoverer.failed_sitemaps:
            logger.warning(f"  Failed sitemaps: {', '.join(discoverer.failed_sitemaps)}")

        logger.info("=" * 70)

        return 0

    except Exception as e:
        logger.error(f"Discovery failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
