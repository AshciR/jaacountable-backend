"""Tests for GleanerRssFeedDiscoverer."""

from unittest.mock import Mock, patch

import pytest
import requests

from src.article_discovery.discoverers.gleaner_rss_discoverer import GleanerRssFeedDiscoverer
from src.article_discovery.models import DiscoveredArticle

# Real RSS feed XML from Jamaica Gleaner (subset for testing)
REAL_GLEANER_RSS_FEED = b'''<?xml version="1.0" encoding="utf-8"?>
<rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0" xml:base="http://jamaica-gleaner.com/">
  <channel>
    <title>Lead Stories</title>
    <link>http://jamaica-gleaner.com/</link>
    <description/>
    <language>en</language>

    <item>
  <title>'Knockout blow' </title>
  <link>http://jamaica-gleaner.com/article/news/20251209/knockout-blow</link>
  <description> The Supreme Court has thrown out an application brought by the People's National Party's Paul Buchanan to overturn the results of the St Andrew West Central general election which he lost to Prime Minister Dr Andrew Holness.  Buchanan, who was the Opposition Party's candidate, filed an application for permission to seek judicial review of the decision of the Constituted Authority not to apply to the Election Court to void the results of the September 3 poll.</description>
  <pubDate>Tue, 09 Dec 2025 00:06:09 -0500</pubDate>
    <dc:creator>Kimone Francis/Senior Staff Reporter</dc:creator>
    <guid isPermaLink="true">http://jamaica-gleaner.com/article/news/20251209/knockout-blow</guid>
    </item>
<item>
  <title>'We intend to fight this' </title>
  <link>http://jamaica-gleaner.com/article/news/20251209/we-intend-fight</link>
  <description> State Minister for Finance and the Public Service Zavia Mayne has filed a lawsuit against the Integrity Commission (IC), asking the court to quash the ruling of the director of corruption prosecution that he should be charged for breaching Section 43(1)(6) of the Integrity Commission Act. With three senior directors and the IC named as respondents, Mayne also wants the court to rescind the July 14, 2025 investigation report tabled last week in Parliament.</description>
  <pubDate>Tue, 09 Dec 2025 00:06:09 -0500</pubDate>
    <dc:creator>Edmond Campbell/Senior Staff Reporter</dc:creator>
    <guid isPermaLink="true">http://jamaica-gleaner.com/article/news/20251209/we-intend-fight</guid>
    </item>
<item>
  <title>Union Acres homeowners threaten legal action over hurricane losses </title>
  <link>http://jamaica-gleaner.com/article/news/20251209/union-acres-homeowners-threaten-legal-action-over-hurricane-losses</link>
  <description> Homeowners in Union Acres, St James, whose newly built properties were torn up by Hurricane Melissa in October, have served notice that they will use litigation in an effort to force the developer to pay for the catastrophic losses they sustained. The National Housing Trust (NHT) has confirmed that approximately 40 of the 144 two-bedroom houses sustained "varying degrees of damage".</description>
  <pubDate>Tue, 09 Dec 2025 00:06:24 -0500</pubDate>
    <dc:creator>Kimone Francis/Senior Staff Reporter</dc:creator>
    <guid isPermaLink="true">http://jamaica-gleaner.com/article/news/20251209/union-acres-homeowners-threaten-legal-action-over-hurricane-losses</guid>
    </item>
<item>
  <title>Jamaican man dies after being struck by moped driver in Queens </title>
  <link>http://jamaica-gleaner.com/article/news/20251209/jamaican-man-dies-after-being-struck-moped-driver-queens</link>
  <description> A 68-year-old Jamaica-born man was struck and killed by a moped while standing on the street in a section of Queens, New York, in the United States on Friday. Dead is former corrections officer Trevor Lloyd Samuels, who was in the marked crosswalk when he was struck by the moped at East 93rd Avenue and 168th Street. The incident occurred just days before Samuels was reportedly scheduled to travel to Jamaica today. Samuels was planning to take his young daughter with him from Jamaica to New York to celebrate the upcoming Christmas holidays.</description>
  <pubDate>Tue, 09 Dec 2025 00:06:06 -0500</pubDate>
    <dc:creator/>
    <guid isPermaLink="true">http://jamaica-gleaner.com/article/news/20251209/jamaican-man-dies-after-being-struck-moped-driver-queens</guid>
    </item>

  </channel>
</rss>'''


class TestGleanerRssFeedDiscovererHappyPath:
    """Test successful RSS discovery scenarios."""

    @pytest.mark.asyncio
    @patch('requests.get')
    async def test_discover_returns_discovered_articles(self, mock_get):
        # Given: A valid RSS feed URL and news source ID
        mock_response = Mock()
        mock_response.content = REAL_GLEANER_RSS_FEED
        mock_get.return_value = mock_response

        discoverer = GleanerRssFeedDiscoverer()
        news_source_id = 1

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id)

        # Then: Returns list of DiscoveredArticle instances
        assert isinstance(articles, list)
        assert len(articles) == 4
        assert all(isinstance(a, DiscoveredArticle) for a in articles)

    @pytest.mark.asyncio
    @patch('requests.get')
    async def test_discovered_articles_use_parameterized_section(self, mock_get):
        # Given: RSS discoverer with custom section name
        mock_response = Mock()
        mock_response.content = REAL_GLEANER_RSS_FEED
        mock_get.return_value = mock_response

        discoverer = GleanerRssFeedDiscoverer(section="custom-section")

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=1)

        # Then: All articles have the custom section name
        assert len(articles) == 4
        assert all(a.section == "custom-section" for a in articles)

    @pytest.mark.asyncio
    @patch('requests.get')
    async def test_discovered_articles_have_required_fields(self, mock_get):
        # Given: A valid RSS feed
        mock_response = Mock()
        mock_response.content = REAL_GLEANER_RSS_FEED
        mock_get.return_value = mock_response

        discoverer = GleanerRssFeedDiscoverer()

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=1)

        # Then: Each article has required fields
        assert len(articles) == 4
        for article in articles:
            assert article.url.startswith("http")
            assert article.news_source_id == 1
            assert article.section == "lead-stories"
            assert article.discovered_at.tzinfo is not None  # Timezone-aware

    @pytest.mark.asyncio
    @patch('requests.get')
    async def test_discovered_articles_have_optional_fields_populated(self, mock_get):
        # Given: A valid RSS feed with title and published_date
        mock_response = Mock()
        mock_response.content = REAL_GLEANER_RSS_FEED
        mock_get.return_value = mock_response

        discoverer = GleanerRssFeedDiscoverer()

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=1)

        # Then: All articles should have optional fields populated
        assert len(articles) == 4
        for article in articles:
            assert article.title is not None
            assert article.published_date is not None
            assert article.published_date.tzinfo is not None  # Timezone-aware

    @pytest.mark.asyncio
    @patch('requests.get')
    async def test_discover_parses_first_article_metadata_correctly(self, mock_get):
        # Given: RSS feed with known data
        mock_response = Mock()
        mock_response.content = REAL_GLEANER_RSS_FEED
        mock_get.return_value = mock_response

        discoverer = GleanerRssFeedDiscoverer()

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=1)

        # Then: First article has correct metadata
        first_article = articles[0]
        assert first_article.title == "'Knockout blow'"  # Trailing space stripped
        assert first_article.url == "http://jamaica-gleaner.com/article/news/20251209/knockout-blow"
        assert first_article.section == "lead-stories"
        assert first_article.news_source_id == 1

    @pytest.mark.asyncio
    @patch('requests.get')
    async def test_discover_parses_second_article_metadata_correctly(self, mock_get):
        # Given: RSS feed with known data
        mock_response = Mock()
        mock_response.content = REAL_GLEANER_RSS_FEED
        mock_get.return_value = mock_response

        discoverer = GleanerRssFeedDiscoverer()

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=1)

        # Then: Second article has correct metadata
        second_article = articles[1]
        assert second_article.title == "'We intend to fight this'"  # Trailing space stripped
        assert second_article.url == "http://jamaica-gleaner.com/article/news/20251209/we-intend-fight"
        assert second_article.section == "lead-stories"
        assert second_article.news_source_id == 1

    @pytest.mark.asyncio
    @patch('requests.get')
    async def test_discover_deduplicates_articles_by_url(self, mock_get):
        # Given: RSS feed with duplicate URLs
        duplicate_feed = b'''<?xml version="1.0" encoding="utf-8"?>
        <rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
            <channel>
                <title>Test Feed</title>
                <item>
                    <title>Article 1</title>
                    <link>http://example.com/article1</link>
                    <pubDate>Mon, 09 Dec 2025 12:00:00 -0500</pubDate>
                </item>
                <item>
                    <title>Article 1 Duplicate</title>
                    <link>http://example.com/article1</link>
                    <pubDate>Mon, 09 Dec 2025 13:00:00 -0500</pubDate>
                </item>
                <item>
                    <title>Article 2</title>
                    <link>http://example.com/article2</link>
                    <pubDate>Mon, 09 Dec 2025 14:00:00 -0500</pubDate>
                </item>
            </channel>
        </rss>'''
        mock_response = Mock()
        mock_response.content = duplicate_feed
        mock_get.return_value = mock_response

        discoverer = GleanerRssFeedDiscoverer()

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=1)

        # Then: Returns only unique URLs (first occurrence kept)
        assert len(articles) == 2
        urls = [a.url for a in articles]
        assert len(urls) == len(set(urls))  # All URLs are unique
        assert articles[0].title == "Article 1"  # First occurrence kept


class TestGleanerRssFeedDiscovererValidationErrors:
    """Test validation error scenarios."""

    @pytest.mark.asyncio
    async def test_discover_raises_error_for_zero_news_source_id(self):
        # Given: Invalid news source ID (zero)
        discoverer = GleanerRssFeedDiscoverer()

        # When/Then: Raises ValueError
        with pytest.raises(ValueError, match="Invalid news_source_id"):
            await discoverer.discover(news_source_id=0)

    @pytest.mark.asyncio
    async def test_discover_raises_error_for_negative_news_source_id(self):
        # Given: Invalid news source ID (negative)
        discoverer = GleanerRssFeedDiscoverer()

        # When/Then: Raises ValueError
        with pytest.raises(ValueError, match="Invalid news_source_id"):
            await discoverer.discover(news_source_id=-1)


class TestGleanerRssFeedDiscovererNetworkErrors:
    """Test network error handling and retry logic."""

    @pytest.mark.asyncio
    async def test_discover_raises_error_for_unreachable_feed(self):
        # Given: Invalid feed URL (no mock, will actually fail)
        discoverer = GleanerRssFeedDiscoverer(
            feed_url="https://invalid-url-that-does-not-exist.test",
            max_retries=2,  # Fewer retries for faster test
            base_backoff=0.1  # Shorter backoff for faster test
        )

        # When/Then: Raises RuntimeError after retries
        with pytest.raises(RuntimeError, match="Failed to fetch RSS feed after 2 attempts"):
            await discoverer.discover(news_source_id=1)

    @pytest.mark.asyncio
    @patch('requests.get')
    async def test_discover_retries_on_network_failure(self, mock_get):
        # Given: Network fails twice, then succeeds
        mock_response = Mock()
        mock_response.content = REAL_GLEANER_RSS_FEED

        mock_get.side_effect = [
            requests.RequestException("Network error"),
            requests.RequestException("Network error"),
            mock_response
        ]

        discoverer = GleanerRssFeedDiscoverer(
            feed_url="https://example.com/feed.xml",
            max_retries=3,
            base_backoff=0.01  # Very short for testing
        )

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=1)

        # Then: Succeeds after retries
        assert len(articles) == 4
        assert mock_get.call_count == 3  # Failed twice, succeeded third time

    @pytest.mark.asyncio
    @patch('requests.get')
    async def test_discover_respects_max_retries(self, mock_get):
        # Given: Network always fails
        mock_get.side_effect = requests.RequestException("Network error")

        discoverer = GleanerRssFeedDiscoverer(
            feed_url="https://example.com/feed.xml",
            max_retries=3,
            base_backoff=0.01  # Very short for testing
        )

        # When/Then: Raises error after max retries
        with pytest.raises(RuntimeError, match="Failed to fetch RSS feed after 3 attempts"):
            await discoverer.discover(news_source_id=1)

        # Verify it tried exactly max_retries times
        assert mock_get.call_count == 3


class TestGleanerRssFeedDiscovererEdgeCases:
    """Test edge cases and unusual scenarios."""

    @pytest.mark.asyncio
    @patch('requests.get')
    async def test_discover_handles_empty_feed(self, mock_get):
        # Given: Empty RSS feed
        mock_response = Mock()
        mock_response.content = b'''<?xml version="1.0" encoding="utf-8"?>
        <rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
            <channel>
                <title>Test Feed</title>
            </channel>
        </rss>'''
        mock_get.return_value = mock_response

        discoverer = GleanerRssFeedDiscoverer(feed_url="https://example.com/feed.xml")

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=1)

        # Then: Returns empty list
        assert articles == []

    @pytest.mark.asyncio
    @patch('requests.get')
    async def test_discover_skips_entries_with_missing_url(self, mock_get):
        # Given: RSS feed with entry missing required 'link' field
        mock_response = Mock()
        mock_response.content = b'''<?xml version="1.0" encoding="utf-8"?>
        <rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
            <channel>
                <title>Test Feed</title>
                <item>
                    <title>Article without URL</title>
                    <pubDate>Mon, 09 Dec 2025 12:00:00 -0500</pubDate>
                </item>
                <item>
                    <title>Valid Article</title>
                    <link>http://example.com/article2</link>
                    <pubDate>Mon, 09 Dec 2025 13:00:00 -0500</pubDate>
                </item>
            </channel>
        </rss>'''
        mock_get.return_value = mock_response

        discoverer = GleanerRssFeedDiscoverer(feed_url="https://example.com/feed.xml")

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=1)

        # Then: Returns only the valid article (skips malformed one)
        assert len(articles) == 1
        assert articles[0].title == "Valid Article"
        assert articles[0].url == "http://example.com/article2"

    @pytest.mark.asyncio
    @patch('requests.get')
    async def test_discover_handles_entries_with_empty_title(self, mock_get):
        # Given: RSS feed with entry with empty title
        mock_response = Mock()
        mock_response.content = b'''<?xml version="1.0" encoding="utf-8"?>
        <rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
            <channel>
                <title>Test Feed</title>
                <item>
                    <title></title>
                    <link>http://example.com/article1</link>
                    <pubDate>Mon, 09 Dec 2025 12:00:00 -0500</pubDate>
                </item>
            </channel>
        </rss>'''
        mock_get.return_value = mock_response

        discoverer = GleanerRssFeedDiscoverer(feed_url="https://example.com/feed.xml")

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=1)

        # Then: Article is created with title=None
        assert len(articles) == 1
        assert articles[0].title is None  # Empty title becomes None
        assert articles[0].url == "http://example.com/article1"

    @pytest.mark.asyncio
    @patch('requests.get')
    async def test_discover_handles_entries_without_published_date(self, mock_get):
        # Given: RSS feed with entry missing published date
        mock_response = Mock()
        mock_response.content = b'''<?xml version="1.0" encoding="utf-8"?>
        <rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
            <channel>
                <title>Test Feed</title>
                <item>
                    <title>Article without date</title>
                    <link>http://example.com/article1</link>
                </item>
            </channel>
        </rss>'''
        mock_get.return_value = mock_response

        discoverer = GleanerRssFeedDiscoverer(feed_url="https://example.com/feed.xml")

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=1)

        # Then: Article is created with published_date=None
        assert len(articles) == 1
        assert articles[0].published_date is None
        assert articles[0].url == "http://example.com/article1"

    @pytest.mark.asyncio
    @patch('requests.get')
    async def test_discover_raises_error_for_invalid_xml(self, mock_get):
        # Given: Invalid XML (not well-formed)
        mock_response = Mock()
        mock_response.content = b'<rss><channel><item>broken xml'
        mock_get.return_value = mock_response

        discoverer = GleanerRssFeedDiscoverer(feed_url="https://example.com/feed.xml")

        # When/Then: Raises RuntimeError for invalid feed format
        with pytest.raises(RuntimeError, match="Invalid RSS feed format"):
            await discoverer.discover(news_source_id=1)

    @pytest.mark.asyncio
    @patch('requests.get')
    async def test_discover_handles_empty_dc_creator(self, mock_get):
        # Given: Real Gleaner feed includes items with empty dc:creator
        mock_response = Mock()
        mock_response.content = REAL_GLEANER_RSS_FEED
        mock_get.return_value = mock_response

        discoverer = GleanerRssFeedDiscoverer()

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=1)

        # Then: Article with empty dc:creator is still parsed successfully
        # (Fourth article has empty dc:creator)
        assert len(articles) == 4
        assert articles[3].title == "Jamaican man dies after being struck by moped driver in Queens"  # Trailing space stripped
