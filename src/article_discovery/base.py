"""Base protocol for article discovery strategies."""
from typing import Protocol
from .models import DiscoveredArticle


class ArticleDiscovery(Protocol):
    """
    Protocol for article discovery strategies using structural subtyping.

    This Protocol defines the interface for article discoverers without
    requiring inheritance. Any class that implements the discover() method
    with the correct signature can be used as an ArticleDiscovery strategy.

    This enables the Strategy Pattern with maximum flexibility:
    - No need to inherit from a base class
    - Duck typing with type safety
    - Easy to add new discovery strategies

    Discovery Strategies Examples:
        - SitemapDiscoverer: Parse sitemap.xml files
        - RssFeedDiscoverer: Parse RSS/Atom feeds
        - SectionScraperDiscoverer: Scrape article listing pages
        - RecursiveCrawlerDiscoverer: Follow links recursively

    Example:
        class MySitemapDiscoverer:  # No inheritance needed!
            async def discover(self, news_source_id: int) -> list[DiscoveredArticle]:
                # Implementation here
                pass

        # MySitemapDiscoverer satisfies ArticleDiscovery Protocol
    """

    async def discover(self, news_source_id: int) -> list[DiscoveredArticle]:
        """
        Discover articles from a news source.

        Args:
            news_source_id: Database ID of the news source to discover from
                (used to query news_sources table for base_url, crawl_delay, etc.)

        Returns:
            List of DiscoveredArticle instances representing found articles

        Raises:
            ValueError: If news_source_id is invalid or source not found
            RuntimeError: If discovery process fails (network errors, parsing errors)

        Notes:
            - Implementation should respect crawl_delay from news_sources table
            - Should handle pagination if applicable
            - Should deduplicate URLs within a single discovery run
            - May query articles table to skip already-stored URLs (optional)
        """
        ...
