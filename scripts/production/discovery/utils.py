"""Shared utilities for production discovery scripts."""

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from botocore.client import BaseClient
from config.log_config import configure_logging  # noqa: F401 — re-exported for scripts
from loguru import logger

from config.database import DatabaseConfig
from src.article_discovery.models import DiscoveredArticle
from src.article_persistence.repositories.article_repository import ArticleRepository
from src.storage.s3 import upload_file


def write_jsonl(articles: list[DiscoveredArticle], output_path: Path) -> None:
    """Write discovered articles to a JSONL file.

    Each line is a JSON object representing a DiscoveredArticle.
    Uses Pydantic's model_dump(mode='json') to serialize datetimes to ISO 8601.

    Args:
        articles: List of articles to write.
        output_path: Path to output JSONL file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for article in articles:
            f.write(json.dumps(article.model_dump(mode="json"), ensure_ascii=False) + "\n")

    logger.info(f"Wrote {len(articles)} articles to {output_path}")


def upload_jsonl_to_s3(
    client: BaseClient,
    local_path: Path,
    bucket: str,
    news_source: str,
    date_str: str,
) -> None:
    """Upload a JSONL discovery file to S3.

    The object key follows the convention: {news_source}/{date_str}.jsonl

    Args:
        client: Boto3 S3 client.
        local_path: Path to the local JSONL file to upload.
        bucket: Target S3 bucket name.
        news_source: News source identifier used as the top-level folder (e.g. "gleaner").
        date_str: Date string used as the filename stem (e.g. "2026-04-01").

    Raises:
        botocore.exceptions.BotoCoreError: On upload failure.
    """
    key = f"{news_source}/{date_str}.jsonl"
    upload_file(client, local_path, bucket, key, content_type="application/x-ndjson")


def upload_log_to_s3(
    client: BaseClient,
    local_path: Path,
    bucket: str,
    news_source: str,
    timestamp: str,
) -> None:
    """Upload a log file to S3.

    The object key follows the convention: {news_source}/logs/{timestamp}.log

    Args:
        client: Boto3 S3 client.
        local_path: Path to the local log file to upload.
        bucket: Target S3 bucket name.
        news_source: News source identifier used as the top-level folder (e.g. "gleaner").
        timestamp: Timestamp string used as the filename stem (e.g. "2026-04-01_12-30-00").

    Raises:
        botocore.exceptions.BotoCoreError: On upload failure.
    """
    key = f"{news_source}/logs/{timestamp}.log"
    upload_file(client, local_path, bucket, key, content_type="text/plain")


async def filter_existing_articles(
    articles: list[DiscoveredArticle],
    db: DatabaseConfig,
    article_repo: ArticleRepository,
) -> list[DiscoveredArticle]:
    """
    Query the DB for already-stored URLs and return only the new articles.

    Args:
        articles: Discovered articles to filter.
        db: DatabaseConfig instance used to acquire a connection.
        article_repo: ArticleRepository used to batch-query existing URLs.

    Returns:
        Subset of articles whose URLs are not yet in the database.
    """
    logger.debug(f"skip-existing: querying DB for {len(articles)} discovered URLs")

    async with db.connection() as conn:
        all_urls = [a.url for a in articles]
        existing_urls = await article_repo.get_existing_urls(conn, all_urls)

    logger.debug(f"skip-existing: {len(existing_urls)} existing URLs found in DB")
    for url in sorted(existing_urls):
        logger.debug(f"skip-existing: already stored → {url}")

    before = len(articles)
    filtered = [a for a in articles if a.url not in existing_urls]
    logger.info(
        f"skip-existing: {len(existing_urls)} already stored, "
        f"{before - len(filtered)} filtered out, {len(filtered)} remain"
    )
    return filtered


def build_failure_stubs(
    failed_items: list[str],
    news_source_id: int,
    *,
    url_builder: Callable[[str], str],
    section: str,
    date_parser: Callable[[str], datetime | None] | None = None,
) -> list[DiscoveredArticle]:
    """Create stub DiscoveredArticle entries for failed items.

    These are NOT real articles — placeholders that identify which items failed
    so they can be retried. Title format is "FAILED: {item}".

    Args:
        failed_items: Identifiers that failed (date strings, page names, sitemap filenames…)
        news_source_id: Database ID of the news source.
        url_builder: Maps an item identifier to its canonical URL.
        section: Section name assigned to all stubs.
        date_parser: Optional callable to parse an item identifier into a
            timezone-aware datetime. If None, published_date is set to None.
    """
    now = datetime.now(timezone.utc)
    return [
        DiscoveredArticle(
            url=url_builder(item),
            news_source_id=news_source_id,
            section=section,
            discovered_at=now,
            title=f"FAILED: {item}",
            published_date=date_parser(item) if date_parser else None,
        )
        for item in failed_items
    ]
