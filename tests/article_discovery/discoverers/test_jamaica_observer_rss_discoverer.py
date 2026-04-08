"""Tests for JamaicaObserverRssFeedDiscoverer."""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.article_discovery.discoverers.jamaica_observer_rss_discoverer import (
    JamaicaObserverRssFeedDiscoverer,
)
from src.article_discovery.models import DiscoveredArticle, RssFeedConfig

# Real RSS feed XML from Jamaica Observer latest-news feed (subset for testing)
# Source: https://www.jamaicaobserver.com/app-feed-category/?category=latest-news
REAL_OBSERVER_LATEST_NEWS_RSS_FEED = b'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
    xmlns:media="http://search.yahoo.com/mrss/">
<channel>
    <title>Jamaica Observer</title>
    <link>https://www.jamaicaobserver.com/jamaicaobserver/news</link>
    <description></description>

    <item>
        <title>Neita Garvey calls for urgent action on prolonged shelter conditions</title>
        <description><![CDATA[<p>KINGSTON, Jamaica - Shadow Minister of Local Government, Natalie Neita Garvey is raising concern about the continued housing of hurricane-affected residents in school shelters months after the passage of Hurricane Melissa.</p>]]></description>
        <guid>https://www.jamaicaobserver.com/2026/04/08/neita-garvey-calls-urgent-action-prolonged-shelter-conditions/</guid>
        <media:content type="image/jpeg" url="https://www.jamaicaobserver.com/jamaicaobserver/news/wp-content/uploads/sites/4/2020/06/8d4e0eaf2c54a986d95ff393bdaf45d1.jpg" height="329" width="501"></media:content>
        <link>https://www.jamaicaobserver.com/2026/04/08/neita-garvey-calls-urgent-action-prolonged-shelter-conditions/</link>
        <pubDate>Wed, 08 Apr 2026 21:57:15 +0000</pubDate>
    </item>

    <item>
        <title>Chronic Law and Pimpdon Records climb to number 4 on US itunes reggae chart</title>
        <description><![CDATA[<p>Dancehall star Chronic Law and producer Pimpdon Records have many reasons to celebrate at present.</p>]]></description>
        <guid>https://www.jamaicaobserver.com/2026/04/08/chronic-law-pimpdon-records-climb-number-4-us-itunes-reggae-chart/</guid>
        <media:content type="image/png" url="https://www.jamaicaobserver.com/jamaicaobserver/news/wp-content/uploads/sites/4/2026/04/Copy-of-Copy-of-Untitled-86.png" height="576" width="1024"></media:content>
        <link>https://www.jamaicaobserver.com/2026/04/08/chronic-law-pimpdon-records-climb-number-4-us-itunes-reggae-chart/</link>
        <pubDate>Wed, 08 Apr 2026 21:52:58 +0000</pubDate>
    </item>

    <item>
        <title>McKenzie calls on JTA president to provide evidence of alleged exposure of students to sexual acts at shelters</title>
        <description><![CDATA[<p>KINGSTON, Jamaica - Local Government Minister Desmond McKenzie has called on the president of the Jamaica Teachers' Association (JTA) to provide evidence.</p>]]></description>
        <guid>https://www.jamaicaobserver.com/2026/04/08/mckenzie-calls-jta-president-provide-evidence-alleged-exposure-students-sexual-acts-shelters/</guid>
        <media:content type="image/jpeg" url="https://www.jamaicaobserver.com/jamaicaobserver/news/wp-content/uploads/sites/4/2025/10/image_1-368.jpg" height="956" width="666"></media:content>
        <link>https://www.jamaicaobserver.com/2026/04/08/mckenzie-calls-jta-president-provide-evidence-alleged-exposure-students-sexual-acts-shelters/</link>
        <pubDate>Wed, 08 Apr 2026 21:45:07 +0000</pubDate>
    </item>

    <item>
        <title>Atletico punish 10-man Barcelona, take control of Champions League tie</title>
        <description><![CDATA[<p>BARCELONA, Spain (AFP) -- Julian Alvarez and Alexander Sorloth's goals earned Atletico Madrid a commanding 2-0 lead over 10-man Barcelona.</p>]]></description>
        <guid>https://www.jamaicaobserver.com/2026/04/08/atletico-punish-10-man-barcelona-take-control-champions-league-tie/</guid>
        <media:content type="image/jpeg" url="https://www.jamaicaobserver.com/jamaicaobserver/news/wp-content/uploads/sites/4/2026/04/lamine-yamal-barcelona-atletico-apr8.jpg" height="689" width="1024"></media:content>
        <link>https://www.jamaicaobserver.com/2026/04/08/atletico-punish-10-man-barcelona-take-control-champions-league-tie/</link>
        <pubDate>Wed, 08 Apr 2026 21:44:33 +0000</pubDate>
    </item>

</channel>
</rss>'''

# Real RSS feed XML from Jamaica Observer news feed (subset for testing)
# Source: https://www.jamaicaobserver.com/app-feed-category/?category=news
# Note: Articles 1 and 2 intentionally overlap with the latest-news feed (realistic cross-feed duplication)
REAL_OBSERVER_NEWS_RSS_FEED = b'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
    xmlns:media="http://search.yahoo.com/mrss/">
<channel>
    <title>Jamaica Observer</title>
    <link>https://www.jamaicaobserver.com/jamaicaobserver/news</link>
    <description></description>

    <item>
        <title>Neita Garvey calls for urgent action on prolonged shelter conditions</title>
        <description><![CDATA[<p>KINGSTON, Jamaica - Shadow Minister of Local Government, Natalie Neita Garvey is raising concern about the continued housing of hurricane-affected residents.</p>]]></description>
        <guid>https://www.jamaicaobserver.com/2026/04/08/neita-garvey-calls-urgent-action-prolonged-shelter-conditions/</guid>
        <media:content type="image/jpeg" url="https://www.jamaicaobserver.com/jamaicaobserver/news/wp-content/uploads/sites/4/2020/06/8d4e0eaf2c54a986d95ff393bdaf45d1.jpg" height="329" width="501"></media:content>
        <link>https://www.jamaicaobserver.com/2026/04/08/neita-garvey-calls-urgent-action-prolonged-shelter-conditions/</link>
        <pubDate>Wed, 08 Apr 2026 21:57:15 +0000</pubDate>
    </item>

    <item>
        <title>McKenzie calls on JTA president to provide evidence of alleged exposure of students to sexual acts at shelters</title>
        <description><![CDATA[<p>KINGSTON, Jamaica - Local Government Minister Desmond McKenzie has called on the president of the Jamaica Teachers' Association (JTA) to provide evidence.</p>]]></description>
        <guid>https://www.jamaicaobserver.com/2026/04/08/mckenzie-calls-jta-president-provide-evidence-alleged-exposure-students-sexual-acts-shelters/</guid>
        <media:content type="image/jpeg" url="https://www.jamaicaobserver.com/jamaicaobserver/news/wp-content/uploads/sites/4/2025/10/image_1-368.jpg" height="956" width="666"></media:content>
        <link>https://www.jamaicaobserver.com/2026/04/08/mckenzie-calls-jta-president-provide-evidence-alleged-exposure-students-sexual-acts-shelters/</link>
        <pubDate>Wed, 08 Apr 2026 21:45:07 +0000</pubDate>
    </item>

    <item>
        <title>Cornwall Regional Hospital conducting review after death of baby delivered at hospital</title>
        <description><![CDATA[<p>ST JAMES, Jamaica - The Cornwall Regional Hospital says it is now conducting an urgent review following the death of a baby delivered at the hospital on Good Friday.</p>]]></description>
        <guid>https://www.jamaicaobserver.com/2026/04/08/cornwall-regional-hospital-conducting-review-death-baby-delivered-hospital/</guid>
        <media:content type="image/jpeg" url="https://www.jamaicaobserver.com/jamaicaobserver/news/wp-content/uploads/sites/4/2026/01/image_1-425-1024x768.jpg" height="768" width="1024"></media:content>
        <link>https://www.jamaicaobserver.com/2026/04/08/cornwall-regional-hospital-conducting-review-death-baby-delivered-hospital/</link>
        <pubDate>Wed, 08 Apr 2026 20:21:56 +0000</pubDate>
    </item>

</channel>
</rss>'''


class TestJamaicaObserverRssFeedDiscovererHappyPath:
    """Test successful RSS discovery scenarios."""

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discover_returns_discovered_articles(self, mock_async_client):
        # Given: A valid RSS feed URL and news source ID
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.content = REAL_OBSERVER_LATEST_NEWS_RSS_FEED
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="latest-news")]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)
        news_source_id = 2

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id)

        # Then: Returns list of DiscoveredArticle instances
        assert isinstance(articles, list)
        assert len(articles) == 4
        assert all(isinstance(a, DiscoveredArticle) for a in articles)

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discovered_articles_use_parameterized_section(self, mock_async_client):
        # Given: RSS discoverer with custom section name
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.content = REAL_OBSERVER_LATEST_NEWS_RSS_FEED
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="custom-section")]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=2)

        # Then: All articles have the custom section name
        assert len(articles) == 4
        assert all(a.section == "custom-section" for a in articles)

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discovered_articles_have_required_fields(self, mock_async_client):
        # Given: A valid RSS feed
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.content = REAL_OBSERVER_LATEST_NEWS_RSS_FEED
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="latest-news")]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=2)

        # Then: Each article has required fields
        assert len(articles) == 4
        for article in articles:
            assert article.url.startswith("https://www.jamaicaobserver.com")
            assert article.news_source_id == 2
            assert article.section == "latest-news"
            assert article.discovered_at.tzinfo is not None  # Timezone-aware

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discovered_articles_have_optional_fields_populated(self, mock_async_client):
        # Given: A valid RSS feed with title and published_date
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.content = REAL_OBSERVER_LATEST_NEWS_RSS_FEED
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="latest-news")]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=2)

        # Then: All articles should have optional fields populated
        assert len(articles) == 4
        for article in articles:
            assert article.title is not None
            assert article.published_date is not None
            assert article.published_date.tzinfo is not None  # Timezone-aware

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discover_parses_first_article_metadata_correctly(self, mock_async_client):
        # Given: RSS feed with known data
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.content = REAL_OBSERVER_LATEST_NEWS_RSS_FEED
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="latest-news")]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=2)

        # Then: First article has correct metadata
        first_article = articles[0]
        assert first_article.title == "Neita Garvey calls for urgent action on prolonged shelter conditions"
        assert first_article.url == "https://www.jamaicaobserver.com/2026/04/08/neita-garvey-calls-urgent-action-prolonged-shelter-conditions/"
        assert first_article.section == "latest-news"
        assert first_article.news_source_id == 2

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discover_parses_second_article_metadata_correctly(self, mock_async_client):
        # Given: RSS feed with known data
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.content = REAL_OBSERVER_LATEST_NEWS_RSS_FEED
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="latest-news")]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=2)

        # Then: Second article has correct metadata
        second_article = articles[1]
        assert second_article.title == "Chronic Law and Pimpdon Records climb to number 4 on US itunes reggae chart"
        assert second_article.url == "https://www.jamaicaobserver.com/2026/04/08/chronic-law-pimpdon-records-climb-number-4-us-itunes-reggae-chart/"
        assert second_article.section == "latest-news"
        assert second_article.news_source_id == 2

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discover_deduplicates_articles_by_url(self, mock_async_client):
        # Given: RSS feed with duplicate URLs
        duplicate_feed = b'''<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
            <channel>
                <title>Jamaica Observer</title>
                <item>
                    <title>Article 1</title>
                    <link>https://www.jamaicaobserver.com/2026/04/08/article-1/</link>
                    <pubDate>Wed, 08 Apr 2026 12:00:00 +0000</pubDate>
                </item>
                <item>
                    <title>Article 1 Duplicate</title>
                    <link>https://www.jamaicaobserver.com/2026/04/08/article-1/</link>
                    <pubDate>Wed, 08 Apr 2026 13:00:00 +0000</pubDate>
                </item>
                <item>
                    <title>Article 2</title>
                    <link>https://www.jamaicaobserver.com/2026/04/08/article-2/</link>
                    <pubDate>Wed, 08 Apr 2026 14:00:00 +0000</pubDate>
                </item>
            </channel>
        </rss>'''
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.content = duplicate_feed
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="latest-news")]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=2)

        # Then: Returns only unique URLs (first occurrence kept)
        assert len(articles) == 2
        urls = [a.url for a in articles]
        assert len(urls) == len(set(urls))  # All URLs are unique
        assert articles[0].title == "Article 1"  # First occurrence kept


class TestJamaicaObserverRssFeedDiscovererValidationErrors:
    """Test validation error scenarios."""

    @pytest.mark.asyncio
    async def test_discover_raises_error_for_zero_news_source_id(self):
        # Given: Invalid news source ID (zero)
        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="latest-news")]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)

        # When/Then: Raises ValueError
        with pytest.raises(ValueError, match="Invalid news_source_id"):
            await discoverer.discover(news_source_id=0)

    @pytest.mark.asyncio
    async def test_discover_raises_error_for_negative_news_source_id(self):
        # Given: Invalid news source ID (negative)
        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="latest-news")]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)

        # When/Then: Raises ValueError
        with pytest.raises(ValueError, match="Invalid news_source_id"):
            await discoverer.discover(news_source_id=-1)


class TestJamaicaObserverRssFeedDiscovererNetworkErrors:
    """Test network error handling and retry logic."""

    @pytest.mark.asyncio
    async def test_discover_returns_empty_list_for_unreachable_feed(self):
        # Given: Invalid feed URL (no mock, will actually fail)
        feed_configs = [RssFeedConfig(
            url="https://invalid-url-that-does-not-exist.test",
            section="latest-news"
        )]
        discoverer = JamaicaObserverRssFeedDiscoverer(
            feed_configs=feed_configs,
            max_retries=2,  # Fewer retries for faster test
            base_backoff=0.1  # Shorter backoff for faster test
        )

        # When: Discovering articles from unreachable feed
        articles = await discoverer.discover(news_source_id=2)

        # Then: Returns empty list (fail-soft behavior)
        assert articles == []

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discover_retries_on_network_failure(self, mock_async_client):
        # Given: Network fails twice, then succeeds
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.content = REAL_OBSERVER_LATEST_NEWS_RSS_FEED

        mock_client_instance.get = AsyncMock(side_effect=[
            httpx.HTTPError("Network error"),
            httpx.HTTPError("Network error"),
            mock_response
        ])
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="latest-news")]
        discoverer = JamaicaObserverRssFeedDiscoverer(
            feed_configs=feed_configs,
            max_retries=3,
            base_backoff=0.01  # Very short for testing
        )

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=2)

        # Then: Succeeds after retries
        assert len(articles) == 4
        assert mock_client_instance.get.call_count == 3  # Failed twice, succeeded third time

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discover_respects_max_retries(self, mock_async_client):
        # Given: Network always fails
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(side_effect=httpx.HTTPError("Network error"))
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="latest-news")]
        discoverer = JamaicaObserverRssFeedDiscoverer(
            feed_configs=feed_configs,
            max_retries=3,
            base_backoff=0.01  # Very short for testing
        )

        # When: Attempting to discover articles
        articles = await discoverer.discover(news_source_id=2)

        # Then: Returns empty list (fail-soft) and retries exactly max_retries times
        assert articles == []
        assert mock_client_instance.get.call_count == 3


class TestJamaicaObserverRssFeedDiscovererEdgeCases:
    """Test edge cases and unusual scenarios."""

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discover_handles_empty_feed(self, mock_async_client):
        # Given: Empty RSS feed
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.content = b'''<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
            <channel>
                <title>Jamaica Observer</title>
            </channel>
        </rss>'''
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="latest-news")]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=2)

        # Then: Returns empty list
        assert articles == []

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discover_skips_entries_with_missing_url(self, mock_async_client):
        # Given: RSS feed with entry missing required 'link' field
        mock_response = Mock()
        mock_response.content = b'''<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
            <channel>
                <title>Jamaica Observer</title>
                <item>
                    <title>Article without URL</title>
                    <pubDate>Wed, 08 Apr 2026 12:00:00 +0000</pubDate>
                </item>
                <item>
                    <title>Valid Article</title>
                    <link>https://www.jamaicaobserver.com/2026/04/08/valid-article/</link>
                    <pubDate>Wed, 08 Apr 2026 13:00:00 +0000</pubDate>
                </item>
            </channel>
        </rss>'''
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="latest-news")]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=2)

        # Then: Returns only the valid article (skips malformed one)
        assert len(articles) == 1
        assert articles[0].title == "Valid Article"
        assert articles[0].url == "https://www.jamaicaobserver.com/2026/04/08/valid-article/"

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discover_handles_entries_with_empty_title(self, mock_async_client):
        # Given: RSS feed with entry with empty title
        mock_response = Mock()
        mock_response.content = b'''<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
            <channel>
                <title>Jamaica Observer</title>
                <item>
                    <title></title>
                    <link>https://www.jamaicaobserver.com/2026/04/08/article-1/</link>
                    <pubDate>Wed, 08 Apr 2026 12:00:00 +0000</pubDate>
                </item>
            </channel>
        </rss>'''
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="latest-news")]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=2)

        # Then: Article is created with title=None
        assert len(articles) == 1
        assert articles[0].title is None  # Empty title becomes None
        assert articles[0].url == "https://www.jamaicaobserver.com/2026/04/08/article-1/"

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discover_handles_entries_without_published_date(self, mock_async_client):
        # Given: RSS feed with entry missing published date
        mock_response = Mock()
        mock_response.content = b'''<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
            <channel>
                <title>Jamaica Observer</title>
                <item>
                    <title>Article without date</title>
                    <link>https://www.jamaicaobserver.com/2026/04/08/article-no-date/</link>
                </item>
            </channel>
        </rss>'''
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="latest-news")]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=2)

        # Then: Article is created with published_date=None
        assert len(articles) == 1
        assert articles[0].published_date is None
        assert articles[0].url == "https://www.jamaicaobserver.com/2026/04/08/article-no-date/"

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discover_returns_empty_list_for_invalid_xml(self, mock_async_client):
        # Given: Invalid XML (not well-formed)
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.content = b'<rss><channel><item>broken xml'
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="latest-news")]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)

        # When: Attempting to discover articles from invalid XML
        articles = await discoverer.discover(news_source_id=2)

        # Then: Returns empty list (fail-soft behavior)
        assert articles == []

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discover_handles_media_content_elements(self, mock_async_client):
        # Given: Observer feeds include media:content elements alongside article links
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.content = REAL_OBSERVER_LATEST_NEWS_RSS_FEED
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [RssFeedConfig(url="https://example.com/feed", section="latest-news")]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=2)

        # Then: All 4 articles are parsed correctly (media:content elements do not interfere)
        assert len(articles) == 4
        # Verify URLs point to article pages, not media files
        for article in articles:
            assert "jamaicaobserver.com" in article.url
            assert not article.url.endswith((".jpg", ".png", ".jpeg"))


class TestJamaicaObserverRssFeedDiscovererMultiFeed:
    """Test multi-feed support."""

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discover_combines_articles_from_multiple_feeds(self, mock_async_client):
        # Given: Two feeds (latest-news and news) where 2 articles overlap
        # latest-news: 4 articles, news: 3 articles, 2 URLs shared → 5 unique
        mock_client_instance = AsyncMock()
        mock_response_latest = Mock()
        mock_response_latest.content = REAL_OBSERVER_LATEST_NEWS_RSS_FEED
        mock_response_news = Mock()
        mock_response_news.content = REAL_OBSERVER_NEWS_RSS_FEED
        mock_client_instance.get = AsyncMock(side_effect=[mock_response_latest, mock_response_news])
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [
            RssFeedConfig(
                url="https://www.jamaicaobserver.com/app-feed-category/?category=latest-news",
                section="latest-news",
            ),
            RssFeedConfig(
                url="https://www.jamaicaobserver.com/app-feed-category/?category=news",
                section="news",
            ),
        ]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=2)

        # Then: Returns deduplicated articles from both feeds (4 + 3 - 2 overlap = 5 unique)
        assert len(articles) == 5

        # Verify articles from latest-news feed
        latest_news_articles = [a for a in articles if a.section == "latest-news"]
        assert len(latest_news_articles) == 4
        assert any("neita-garvey" in a.url for a in latest_news_articles)

        # Verify unique articles from news feed (only Cornwall, since the other 2 are duplicates)
        news_articles = [a for a in articles if a.section == "news"]
        assert len(news_articles) == 1
        assert any("cornwall-regional-hospital" in a.url for a in news_articles)

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discover_deduplicates_across_feeds(self, mock_async_client):
        # Given: Two feeds with the same articles (full overlap)
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.content = REAL_OBSERVER_LATEST_NEWS_RSS_FEED
        mock_client_instance.get = AsyncMock(side_effect=[mock_response, mock_response])
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [
            RssFeedConfig(
                url="https://www.jamaicaobserver.com/app-feed-category/?category=latest-news",
                section="latest-news",
            ),
            RssFeedConfig(
                url="https://www.jamaicaobserver.com/app-feed-category/?category=news",
                section="news",
            ),
        ]
        discoverer = JamaicaObserverRssFeedDiscoverer(feed_configs=feed_configs)

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=2)

        # Then: Returns only unique articles (4, not 8)
        assert len(articles) == 4
        urls = [a.url for a in articles]
        assert len(urls) == len(set(urls))

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_discover_continues_when_one_feed_fails(self, mock_async_client):
        # Given: First feed fails, second succeeds
        mock_client_instance = AsyncMock()
        mock_response_news = Mock()
        mock_response_news.content = REAL_OBSERVER_NEWS_RSS_FEED

        mock_client_instance.get = AsyncMock(side_effect=[
            httpx.HTTPError("Network error"),  # latest-news feed fails
            mock_response_news  # news feed succeeds
        ])
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        mock_async_client.return_value.__aexit__.return_value = AsyncMock()

        feed_configs = [
            RssFeedConfig(
                url="https://www.jamaicaobserver.com/app-feed-category/?category=latest-news",
                section="latest-news",
            ),
            RssFeedConfig(
                url="https://www.jamaicaobserver.com/app-feed-category/?category=news",
                section="news",
            ),
        ]
        discoverer = JamaicaObserverRssFeedDiscoverer(
            feed_configs=feed_configs,
            max_retries=1,  # Minimize retries for faster test
            base_backoff=0.01
        )

        # When: Discovering articles
        articles = await discoverer.discover(news_source_id=2)

        # Then: Returns articles from successful feed only (fail-soft behavior)
        assert len(articles) == 3
        assert all(a.section == "news" for a in articles)
        assert any("cornwall-regional-hospital" in a.url for a in articles)
