"""
Production daily discovery script for Jamaica Gleaner articles via RSS.

Fetches current RSS feeds and exports results to JSONL format for pipeline ingestion.

Usage:
    # Discover with default settings
    PYTHONPATH=. uv run python scripts/production/discovery/discover_gleaner_daily_articles_via_rss.py

    # Discover with custom output directory
    PYTHONPATH=. uv run python scripts/production/discovery/discover_gleaner_daily_articles_via_rss.py \\
        --output-dir /path/to/output

    # Verbose output for debugging
    PYTHONPATH=. uv run python scripts/production/discovery/discover_gleaner_daily_articles_via_rss.py \\
        --verbose

Output:
    - Success file: {output_dir}/gleaner_daily_discovery_{timestamp}.jsonl
    - Failures file: {output_dir}/gleaner_daily_discovery_{timestamp}-failures.jsonl
    - Log file: {output_dir}/gleaner_daily_discovery_{timestamp}.log
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from config.database import db_config
from config.log_config import configure_logging
from scripts.production.discovery.utils import (
    filter_existing_articles,
    write_jsonl,
)
from scripts.production.utils import (
    upload_jsonl_to_s3,
    upload_log_to_s3,
)
from src.article_discovery.discoverers.gleaner_rss_discoverer import GleanerRssFeedDiscoverer
from src.article_discovery.models import RssFeedConfig
from src.article_persistence.repositories.article_repository import ArticleRepository
from src.storage.s3 import get_s3_client

FEED_CONFIGS = [
    RssFeedConfig(url="https://jamaica-gleaner.com/feed/rss.xml", section="lead-stories"),
    RssFeedConfig(url="https://jamaica-gleaner.com/feed/news.xml", section="news"),
]


async def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Discover Jamaica Gleaner daily articles via RSS and export to JSONL"
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
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip S3 upload (useful for local dev without LocalStack running)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Pre-query DB and exclude already-stored URLs from the JSONL output",
    )

    args = parser.parse_args()

    # Setup output directory and logging
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file_path = output_dir / f"gleaner_daily_discovery_{timestamp}.log"

    configure_logging(
        enable_file_logging=True,
        log_file_path=str(log_file_path),
        log_level="DEBUG" if args.verbose else "INFO",
    )

    logger.info(f"Gleaner daily discovery logging to: {log_file_path}")
    logger.debug(f"skip-existing: {'enabled' if args.skip_existing else 'disabled'}")

    # Generate output filenames
    success_path = output_dir / f"gleaner_daily_discovery_{timestamp}.jsonl"
    failures_path = output_dir / f"gleaner_daily_discovery_{timestamp}-failures.jsonl"

    s3 = None
    bucket = None
    exit_code = 0

    try:
        start_time = time.time()

        discoverer = GleanerRssFeedDiscoverer(feed_configs=FEED_CONFIGS)
        articles = await discoverer.discover(news_source_id=args.news_source_id)

        elapsed = time.time() - start_time

        # The daily discovery script wrote all RSS articles to JSONL
        # on every run with no DB check, so articles still in the feed on the
        # 2nd and 3rd cron runs of the day were re-included for classification.
        # Although  --skip-existing in the classification script was a safety net,
        # any gap there (URL mismatch, race condition) would allow redundant
        # extraction and classification.
        #
        # Fix: Added --skip-existing to the discovery script that pre-queries
        # the DB via ArticleRepository.get_existing_urls() and strips
        # already-stored URLs from the JSONL before the classification pipeline runs.
        # The workflow now passes this flag at the discovery step,
        # eliminating redundant processing at the earliest possible stage.
        # Issue: https://github.com/AshciR/jaacountable-backend/issues/210
        if args.skip_existing and articles:
            await db_config.create_pool(min_size=1, max_size=2, command_timeout=30.0)
            articles = await filter_existing_articles(
                articles=articles,
                db=db_config,
                article_repo=ArticleRepository(),
            )

        # Write output files
        write_jsonl(articles, success_path)
        # No explicit failure tracking: the discoverer handles per-feed failures
        # fail-soft internally. With only 2 fixed feeds, selective retry is not
        # useful — re-run the whole script if a feed fails.
        write_jsonl([], failures_path)

        # Upload JSONL files to S3
        if args.skip_upload:
            logger.info("Skipping S3 upload (--skip-upload flag set)")
        else:
            bucket = os.environ["S3_BUCKET"]
            s3 = get_s3_client()
            upload_jsonl_to_s3(
                s3, success_path, bucket, news_source="gleaner", date_str=f"gleaner_daily_discovery_{timestamp}"
            )
            upload_jsonl_to_s3(
                s3, failures_path, bucket, news_source="gleaner", date_str=f"gleaner_daily_discovery_{timestamp}-failures"
            )

        # Summary
        logger.info("=" * 70)
        logger.info("Discovery Summary:")
        logger.info(f"  Total articles discovered: {len(articles)}")
        logger.info(f"  Date: {today}")
        logger.info(f"  Feeds: {', '.join(c.url for c in FEED_CONFIGS)}")
        logger.info(f"  Time elapsed: {elapsed:.2f}s ({elapsed / 60:.2f}m)")
        logger.info(f"  Success file: {success_path}")
        logger.info(f"  Failures file: {failures_path}")
        logger.info(f"  Log file: {log_file_path}")
        if bucket:
            logger.info(f"  S3 location: s3://{bucket}/gleaner/gleaner_daily_discovery_{timestamp}.jsonl")

        # Per-section breakdown
        if articles:
            sections: dict[str, int] = {}
            for article in articles:
                sections[article.section] = sections.get(article.section, 0) + 1
            logger.info("  Articles by section:")
            for section, count in sorted(sections.items()):
                logger.info(f"    {section}: {count}")

        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"Discovery failed: {e}", exc_info=True)
        exit_code = 1

    finally:
        # Flush and close the file sink so the log is fully written before upload
        logger.remove()
        if not args.skip_upload and s3 is not None and bucket is not None:
            try:
                upload_log_to_s3(s3, log_file_path, bucket, news_source="gleaner", timestamp=timestamp, log_type="daily_discovery")
            except Exception as e:
                print(f"Warning: failed to upload log to S3: {e}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
