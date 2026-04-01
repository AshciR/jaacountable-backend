"""Shared utilities for production discovery scripts."""

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from config.log_config import configure_logging  # noqa: F401 — re-exported for scripts
from loguru import logger

from src.article_discovery.models import DiscoveredArticle


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
