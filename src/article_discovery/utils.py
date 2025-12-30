"""Utility functions for article discovery."""

import logging

from src.article_discovery.models import DiscoveredArticle

logger = logging.getLogger(__name__)


def deduplicate_discovered_articles(
    articles: list[DiscoveredArticle],
) -> list[DiscoveredArticle]:
    """
    Deduplicate articles by URL, keeping first occurrence.

    This is a standalone helper function for deduplicating articles
    across multiple discoverers (e.g., when running parallel workers).

    Args:
        articles: List of articles (potentially with duplicates)

    Returns:
        Deduplicated list (first occurrence kept for each URL)

    Example:
        # Combine results from multiple workers
        worker1_articles = await discoverer1.discover(news_source_id=1)
        worker2_articles = await discoverer2.discover(news_source_id=1)
        worker3_articles = await discoverer3.discover(news_source_id=1)

        all_articles = worker1_articles + worker2_articles + worker3_articles
        unique_articles = deduplicate_discovered_articles(all_articles)
    """
    seen_urls: set[str] = set()
    deduplicated: list[DiscoveredArticle] = []

    for article in articles:
        if article.url not in seen_urls:
            seen_urls.add(article.url)
            deduplicated.append(article)
        else:
            logger.debug(f"Duplicate URL found, skipping: {article.url}")

    duplicate_count = len(articles) - len(deduplicated)
    if duplicate_count > 0:
        logger.info(
            f"Deduplication complete: {len(deduplicated)} unique articles "
            f"({duplicate_count} duplicates removed)"
        )

    return deduplicated
