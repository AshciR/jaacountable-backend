"""
Example script demonstrating multi-feed RSS-based article discovery.

This script shows how to use the GleanerRssFeedDiscoverer to discover
articles from multiple Jamaica Gleaner RSS feeds.

Usage:
    uv run python scripts/validate_rss_discovery.py
"""

import asyncio
import logging
from datetime import datetime, timezone
from src.article_discovery.discoverers.gleaner_rss_discoverer import GleanerRssFeedDiscoverer
from src.article_discovery.models import DiscoveredArticle, RssFeedConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Run multi-feed RSS discovery example."""
    logger.info("Starting Multi-Feed RSS Discovery Example")
    logger.info("=" * 70)

    # Configure multiple RSS feeds
    feed_configs = [
        RssFeedConfig(
            url="https://jamaica-gleaner.com/feed/rss.xml",
            section="lead-stories"
        ),
        RssFeedConfig(
            url="https://jamaica-gleaner.com/feed/news.xml",
            section="news"
        )
    ]

    logger.info(f"Configured {len(feed_configs)} RSS feeds:")
    for i, config in enumerate(feed_configs, 1):
        logger.info(f"  {i}. {config.url} (section: {config.section})")
    logger.info("")

    # Initialize the RSS discoverer
    discoverer = GleanerRssFeedDiscoverer(feed_configs=feed_configs)

    try:
        # Discover articles from all RSS feeds
        logger.info("Discovering articles from Jamaica Gleaner RSS feeds...")
        articles: list[DiscoveredArticle] = await discoverer.discover(news_source_id=1)

        # Display results
        logger.info(f"\n✓ Successfully discovered {len(articles)} articles\n")

        for i, article in enumerate(articles, 1):
            logger.info(f"Article {i}:")
            logger.info(f"  Title: {article.title}")
            logger.info(f"  URL: {article.url}")
            logger.info(f"  Section: {article.section}")
            logger.info(f"  Published: {article.published_date}")
            logger.info(f"  Discovered at: {article.discovered_at}")
            logger.info("")

        # Show summary statistics
        logger.info("=" * 70)
        logger.info("Summary:")
        logger.info(f"  Total articles discovered: {len(articles)}")

        # Per-section statistics
        sections = {}
        for article in articles:
            sections[article.section] = sections.get(article.section, 0) + 1

        logger.info("  Articles by section:")
        for section, count in sorted(sections.items()):
            logger.info(f"    {section}: {count}")

        logger.info(f"  Articles with titles: {sum(1 for a in articles if a.title)}")
        logger.info(f"  Articles with dates: {sum(1 for a in articles if a.published_date)}")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"Discovery failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
