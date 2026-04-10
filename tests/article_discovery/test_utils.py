"""Tests for article discovery utility functions."""

from datetime import datetime, timezone

import pytest

from src.article_discovery.models import DiscoveredArticle
from src.article_discovery.utils import deduplicate_discovered_articles, normalize_url


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

    @pytest.mark.asyncio
    async def test_deduplicate_treats_percent_encoded_and_decoded_urls_as_same(self):
        """
        GIVEN two articles with URLs that differ only by percent-encoding (%2e vs .)
        WHEN deduplicate_discovered_articles() is called
        THEN it treats them as the same article, keeps only one, and stores the canonical URL
        """
        # Given — the real-world example from issue-213
        encoded_url_article = DiscoveredArticle(
            url="http://jamaica-gleaner.com/index%2ephp/article/news/20260409/ethics-committee-summon-gordon",
            news_source_id=1,
            section="lead-stories",
            discovered_at=datetime.now(timezone.utc),
        )
        decoded_url_article = DiscoveredArticle(
            url="http://jamaica-gleaner.com/article/news/20260409/ethics-committee-summon-gordon",
            news_source_id=1,
            section="lead-stories",
            discovered_at=datetime.now(timezone.utc),
        )

        # When
        deduplicated = deduplicate_discovered_articles(
            [encoded_url_article, decoded_url_article]
        )

        # Then — one article, stored with canonical URL
        assert len(deduplicated) == 1
        assert deduplicated[0].url == (
            "http://jamaica-gleaner.com/article/news/20260409/ethics-committee-summon-gordon"
        )


class TestNormalizeUrl:
    """Test normalize_url() helper function."""

    def test_normalize_url_decodes_percent_encoded_dot(self):
        """
        GIVEN a URL with %2e (percent-encoded dot)
        WHEN normalize_url() is called
        THEN it returns the URL with the dot decoded
        """
        # Given
        url = "http://jamaica-gleaner.com/index%2ephp/article/news/20260409/some-article"

        # When
        result = normalize_url(url)

        # Then
        assert "%2e" not in result
        assert "%2E" not in result

    def test_normalize_url_strips_index_php_prefix(self):
        """
        GIVEN a URL with a /index.php/ path prefix
        WHEN normalize_url() is called
        THEN it strips the /index.php prefix
        """
        # Given
        url = "http://jamaica-gleaner.com/index.php/article/news/20260409/some-article"

        # When
        result = normalize_url(url)

        # Then
        assert result == "http://jamaica-gleaner.com/article/news/20260409/some-article"

    def test_normalize_url_strips_index_php_when_percent_encoded(self):
        """
        GIVEN a URL where index.php is percent-encoded as index%2ephp
        WHEN normalize_url() is called
        THEN it decodes and strips the /index.php prefix
        """
        # Given
        url = "http://jamaica-gleaner.com/index%2ephp/article/news/20260409/ethics-committee-summon-gordon"

        # When
        result = normalize_url(url)

        # Then
        assert result == "http://jamaica-gleaner.com/article/news/20260409/ethics-committee-summon-gordon"

    def test_normalize_url_leaves_clean_urls_unchanged(self):
        """
        GIVEN a URL that is already in canonical form
        WHEN normalize_url() is called
        THEN it returns the URL unchanged
        """
        # Given
        url = "http://jamaica-gleaner.com/article/news/20260409/ethics-committee-summon-gordon"

        # When
        result = normalize_url(url)

        # Then
        assert result == url

    def test_normalize_url_is_idempotent(self):
        """
        GIVEN a URL with percent-encoding and index.php prefix
        WHEN normalize_url() is called twice
        THEN both calls return the same result
        """
        # Given
        url = "http://jamaica-gleaner.com/index%2ephp/article/news/20260409/some-article"

        # When
        first_call = normalize_url(url)
        second_call = normalize_url(first_call)

        # Then
        assert first_call == second_call
