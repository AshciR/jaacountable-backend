"""
Example script demonstrating RSS-based article discovery.

This script shows how to use the GleanerRssFeedDiscoverer to discover
articles from the Jamaica Gleaner RSS feed.

Usage:
    uv run python examples/validate_rss_discovery.py
"""

import asyncio
import logging
from datetime import datetime, timezone
from src.article_discovery.discoverers.gleaner_rss_discoverer import GleanerRssFeedDiscoverer
from src.article_discovery.models import DiscoveredArticle

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Run RSS discovery example."""
    logger.info("Starting RSS Discovery Example")
    logger.info("=" * 70)

    # Initialize the RSS discoverer
    discoverer = GleanerRssFeedDiscoverer(
        feed_url="https://jamaica-gleaner.com/feed/rss.xml",
        section="lead-stories",
    )

    try:
        # Discover articles from the RSS feed
        logger.info("Discovering articles from Jamaica Gleaner RSS feed...")
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
