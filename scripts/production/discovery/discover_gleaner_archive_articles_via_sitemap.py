"""
Production discovery script for Jamaica Gleaner articles via sitemap.

Crawls the Drupal sitemap at https://jamaica-gleaner.com/sitemap.xml to discover
News section articles within a given date range.

Usage:
    # Discover Jan 2025 → Feb 2025
    uv run python scripts/production/discovery/discover_gleaner_archive_articles_via_sitemap.py \\
        --start-date 2025-01-01 --end-date 2025-02-28

    # Discover with custom delay and output directory
    uv run python scripts/production/discovery/discover_gleaner_archive_articles_via_sitemap.py \\
        --start-date 2025-01-01 --end-date 2025-02-28 \\
        --delay 2.0 --output-dir /path/to/output

    # Verbose output for debugging
    uv run python scripts/production/discovery/discover_gleaner_archive_articles_via_sitemap.py \\
        --start-date 2025-01-01 --end-date 2025-02-28 --verbose

Output:
    - Success file: {output_dir}/gleaner_sitemap_{start_date}_to_{end_date}.jsonl
    - Failures file: {output_dir}/gleaner_sitemap_{start_date}_to_{end_date}-failures.jsonl
    - Log file: {output_dir}/gleaner_sitemap_discovery_{timestamp}.log
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
from src.article_discovery.discoverers.jamaica_gleaner_sitemap_discoverer import (
    JamaicaGleanerSitemapDiscoverer,
)


async def main() -> int:
    """Main entry point."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Discover Jamaica Gleaner news articles via sitemap and export to JSONL"
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
        help="Delay between sitemap page requests in seconds (default: 1.5)",
    )
    parser.add_argument(
        "--news-source-id",
        type=int,
        default=1,
        help="Database ID of news source (default: 1 = Jamaica Gleaner)",
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
    log_file_path = output_dir / f"gleaner_sitemap_discovery_{timestamp}.log"

    configure_logging(
        enable_file_logging=True,
        log_file_path=str(log_file_path),
        log_level="DEBUG" if args.verbose else "INFO",
    )

    logger.info(f"Jamaica Gleaner sitemap discovery logging to: {log_file_path}")

    # Generate output filenames
    date_range_str = f"{args.start_date}_to_{args.end_date}"
    success_path = output_dir / f"gleaner_sitemap_{date_range_str}.jsonl"
    failures_path = output_dir / f"gleaner_sitemap_{date_range_str}-failures.jsonl"

    # Run discovery
    try:
        start_time = time.time()

        discoverer = JamaicaGleanerSitemapDiscoverer(
            start_date=start_date,
            end_date=end_date,
            crawl_delay=args.delay,
        )

        articles = await discoverer.discover(news_source_id=args.news_source_id)
        failure_stubs = build_failure_stubs(
            discoverer.failed_sitemaps,
            args.news_source_id,
            url_builder=lambda p: f"https://jamaica-gleaner.com/sitemap.xml?{p}",
            section="sitemap",
        )

        elapsed = time.time() - start_time

        # Write output files
        write_jsonl(articles, success_path)
        write_jsonl(failure_stubs, failures_path)

        # Summary
        logger.info("=" * 70)
        logger.info("Discovery Summary:")
        logger.info(f"  Total articles discovered: {len(articles)}")
        logger.info(f"  Failed sitemap pages: {len(discoverer.failed_sitemaps)}")
        logger.info(f"  Date range: {args.start_date} to {args.end_date}")
        logger.info(f"  Crawl delay: {args.delay}s")
        logger.info(f"  Time elapsed: {elapsed:.2f}s ({elapsed / 60:.2f}m)")
        logger.info(f"  Success file: {success_path}")
        logger.info(f"  Failures file: {failures_path}")
        logger.info(f"  Log file: {log_file_path}")

        if discoverer.failed_sitemaps:
            logger.warning(f"  Failed pages: {', '.join(discoverer.failed_sitemaps)}")

        logger.info("=" * 70)

        return 0

    except Exception as e:
        logger.error(f"Discovery failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
