"""Utility functions for article discovery."""

from urllib.parse import unquote, urlparse, urlunparse

from loguru import logger

from src.article_discovery.models import DiscoveredArticle


def normalize_url(url: str) -> str:
    """
    Normalize a URL to its canonical form.

    - Percent-decodes encoded characters (e.g. %2e → .)
    - Strips the /index.php/ front-controller prefix if present

    Args:
        url: Raw URL string (possibly percent-encoded or with index.php prefix)

    Returns:
        Canonical URL string
    """
    decoded = unquote(url)
    parsed = urlparse(decoded)
    path = parsed.path
    if path.startswith("/index.php/"):
        path = path[len("/index.php"):]
    return urlunparse(parsed._replace(path=path))


def deduplicate_discovered_articles(
    articles: list[DiscoveredArticle],
) -> list[DiscoveredArticle]:
    """
    Deduplicate articles by URL, keeping first occurrence.

    URLs are normalized before comparison so that percent-encoded variants
    (e.g. index%2ephp) and /index.php/ prefixes are treated as the same article.
    The stored article always has the canonical (normalized) URL.

    This is a standalone helper function for deduplicating articles
    across multiple discoverers (e.g., when running parallel workers).

    Args:
        articles: List of articles (potentially with duplicates)

    Returns:
        Deduplicated list (first occurrence kept for each URL, URL normalized)

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
        canonical_url = normalize_url(article.url)
        if canonical_url not in seen_urls:
            seen_urls.add(canonical_url)
            deduplicated.append(article.model_copy(update={"url": canonical_url}))
        else:
            logger.debug(f"Duplicate URL found, skipping: {article.url}")

    duplicate_count = len(articles) - len(deduplicated)
    if duplicate_count > 0:
        logger.info(
            f"Deduplication complete: {len(deduplicated)} unique articles "
            f"({duplicate_count} duplicates removed)"
        )

    return deduplicated
