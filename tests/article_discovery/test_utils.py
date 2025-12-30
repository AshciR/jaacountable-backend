"""Tests for article discovery utility functions."""

from datetime import datetime, timezone

import pytest

from src.article_discovery.models import DiscoveredArticle
from src.article_discovery.utils import deduplicate_discovered_articles


class TestDeduplicateDiscoveredArticles:
    """Test deduplicate_discovered_articles() helper function."""

    @pytest.mark.asyncio
    async def test_deduplicate_removes_duplicate_urls(self):
        """
        GIVEN multiple articles with duplicate URLs
        WHEN deduplicate_discovered_articles() is called
        THEN it keeps first occurrence of each URL
        """
        # Given
        article1 = DiscoveredArticle(
            url="https://example.com/article1",
            news_source_id=1,
            section="news",
            discovered_at=datetime.now(timezone.utc),
        )
        article2 = DiscoveredArticle(
            url="https://example.com/article2",
            news_source_id=1,
            section="news",
            discovered_at=datetime.now(timezone.utc),
        )
        article1_duplicate = DiscoveredArticle(
            url="https://example.com/article1",  # Duplicate URL
            news_source_id=1,
            section="different-section",
            discovered_at=datetime.now(timezone.utc),
        )

        articles = [article1, article2, article1_duplicate]

        # When
        deduplicated = deduplicate_discovered_articles(articles)

        # Then
        assert len(deduplicated) == 2
        assert deduplicated[0].url == "https://example.com/article1"
        assert deduplicated[1].url == "https://example.com/article2"
        # First occurrence kept (section should be "news", not "different-section")
        assert deduplicated[0].section == "news"

    @pytest.mark.asyncio
    async def test_deduplicate_preserves_order(self):
        """
        GIVEN articles in specific order
        WHEN deduplicate_discovered_articles() is called
        THEN it preserves original order
        """
        # Given
        articles = [
            DiscoveredArticle(
                url=f"https://example.com/article{i}",
                news_source_id=1,
                section="news",
                discovered_at=datetime.now(timezone.utc),
            )
            for i in range(10)
        ]

        # When
        deduplicated = deduplicate_discovered_articles(articles)

        # Then: Order preserved
        assert len(deduplicated) == 10
        for i, article in enumerate(deduplicated):
            assert article.url == f"https://example.com/article{i}"

    @pytest.mark.asyncio
    async def test_deduplicate_handles_empty_list(self):
        """
        GIVEN empty list
        WHEN deduplicate_discovered_articles() is called
        THEN it returns empty list
        """
        # Given
        articles = []

        # When
        deduplicated = deduplicate_discovered_articles(articles)

        # Then
        assert deduplicated == []

    @pytest.mark.asyncio
    async def test_deduplicate_handles_no_duplicates(self):
        """
        GIVEN articles with all unique URLs
        WHEN deduplicate_discovered_articles() is called
        THEN it returns same list
        """
        # Given
        articles = [
            DiscoveredArticle(
                url=f"https://example.com/article{i}",
                news_source_id=1,
                section="news",
                discovered_at=datetime.now(timezone.utc),
            )
            for i in range(5)
        ]

        # When
        deduplicated = deduplicate_discovered_articles(articles)

        # Then
        assert len(deduplicated) == 5
        assert deduplicated == articles
