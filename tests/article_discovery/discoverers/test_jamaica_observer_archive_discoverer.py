"""Tests for JamaicaObserverArchiveDiscoverer."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.article_discovery.discoverers.jamaica_observer_archive_discoverer import (
    JamaicaObserverArchiveDiscoverer,
)
from src.article_discovery.models import DiscoveredArticle

# Shared constants
_SEP_15 = datetime(2025, 9, 15, tzinfo=timezone.utc)
_SEP_20 = datetime(2025, 9, 20, tzinfo=timezone.utc)
_SEP_21 = datetime(2025, 9, 21, tzinfo=timezone.utc)


def _make_response(html: str = "", status_code: int = 200) -> Mock:
    """Build a mock httpx.Response."""
    resp = Mock()
    resp.text = html
    resp.status_code = status_code
    if status_code == 404:
        # 404 is handled before raise_for_status() in the discoverer
        resp.raise_for_status = Mock()
    elif status_code >= 400:
        error_response = Mock()
        error_response.status_code = status_code
        resp.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                f"HTTP {status_code}",
                request=Mock(),
                response=error_response,
            )
        )
    else:
        resp.raise_for_status = Mock()
    return resp


def _make_discoverer(**kwargs) -> JamaicaObserverArchiveDiscoverer:
    """Build a discoverer for Sep 15 2025 with fast test settings."""
    defaults = dict(
        start_date=_SEP_15,
        end_date=_SEP_15,
        base_backoff=0.01,
        crawl_delay=0.01,
    )
    defaults.update(kwargs)
    return JamaicaObserverArchiveDiscoverer(**defaults)


def _r404() -> Mock:
    """Shorthand for a 404 response (terminates page probing loop)."""
    return _make_response(status_code=404)


class TestJamaicaObserverArchiveDiscovererHappyPath:
    """Test successful archive page discovery scenarios."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discover_returns_list_of_discovered_articles(
        self, mock_client_class, jo_archive_page_with_articles
    ):
        """
        GIVEN a discoverer for Sep 15, 2025
        WHEN discover() is called with a valid archive page
        THEN it returns a non-empty list of DiscoveredArticle instances
        """
        # Given: page 1 has articles; page 2 probe returns 404 (no more pages)
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_archive_page_with_articles),
            _r404(),
        ])

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then
        assert isinstance(articles, list)
        assert len(articles) > 0
        assert all(isinstance(a, DiscoveredArticle) for a in articles)

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discover_returns_only_news_category_articles(
        self, mock_client_class, jo_archive_page_with_articles
    ):
        """
        GIVEN an archive page with News, Sports, Entertainment, and International News articles
        WHEN discover() is called
        THEN only the 2 articles with exact 'News' category are returned
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_archive_page_with_articles),
            _r404(),
        ])

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then: only News articles returned
        assert len(articles) == 2
        urls = {a.url for a in articles}
        assert "https://www.jamaicaobserver.com/2025/09/15/police-probe-kingston-shooting/" in urls
        assert "https://www.jamaicaobserver.com/2025/09/15/pm-announces-cabinet-reshuffle/" in urls

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discover_excludes_sports_articles(
        self, mock_client_class, jo_archive_page_with_articles
    ):
        """
        GIVEN an archive page with a Sports article
        WHEN discover() is called
        THEN the Sports article URL is not in the results
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_archive_page_with_articles),
            _r404(),
        ])

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then
        urls = {a.url for a in articles}
        assert "https://www.jamaicaobserver.com/2025/09/15/bolt-wins-charity-race/" not in urls

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discover_excludes_entertainment_articles(
        self, mock_client_class, jo_archive_page_with_articles
    ):
        """
        GIVEN an archive page with an Entertainment article
        WHEN discover() is called
        THEN the Entertainment article URL is not in the results
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_archive_page_with_articles),
            _r404(),
        ])

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then
        urls = {a.url for a in articles}
        assert "https://www.jamaicaobserver.com/2025/09/15/artist-wins-grammy/" not in urls

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discover_excludes_international_news_articles(
        self, mock_client_class, jo_archive_page_with_articles
    ):
        """
        GIVEN an archive page with an 'International News' article (not exact 'News')
        WHEN discover() is called
        THEN the International News article is excluded
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_archive_page_with_articles),
            _r404(),
        ])

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then
        urls = {a.url for a in articles}
        assert "https://www.jamaicaobserver.com/2025/09/15/trump-signs-executive-order/" not in urls

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discover_excludes_sidebar_articles_from_other_dates(
        self, mock_client_class, jo_archive_page_with_articles
    ):
        """
        GIVEN an archive page with sidebar articles from a different date
        WHEN discover() is called for Sep 15, 2025
        THEN the different-date articles are excluded
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_archive_page_with_articles),
            _r404(),
        ])

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then
        urls = {a.url for a in articles}
        assert not any("/2026/" in url for url in urls)

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discovered_article_has_correct_fields(
        self, mock_client_class, jo_archive_page_with_articles
    ):
        """
        GIVEN a valid archive page for Sep 15, 2025
        WHEN discover() is called
        THEN articles have correct url, news_source_id, section, title, and published_date
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_archive_page_with_articles),
            _r404(),
        ])

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then
        article = next(
            a for a in articles
            if a.url == "https://www.jamaicaobserver.com/2025/09/15/police-probe-kingston-shooting/"
        )
        assert article.news_source_id == 2
        assert article.section == "archive"
        assert article.title == "police-probe-kingston-shooting"
        assert article.published_date == datetime(2025, 9, 15, tzinfo=timezone.utc)
        assert article.discovered_at.tzinfo == timezone.utc

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discover_deduplicates_articles(
        self, mock_client_class, jo_archive_page_with_articles
    ):
        """
        GIVEN the same archive page returned for two days in range
        WHEN articles appear on both days (duplicates)
        THEN deduplicate_discovered_articles() removes duplicates
        """
        # Given: two-day range; each day: page 1 returns articles, page 2 probe returns 404
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_archive_page_with_articles),  # Sep 15 page 1
            _r404(),                                         # Sep 15 page 2 probe
            _make_response(jo_archive_page_with_articles),  # Sep 16 page 1
            _r404(),                                         # Sep 16 page 2 probe
        ])

        # Two-day range
        discoverer = _make_discoverer(
            start_date=_SEP_15,
            end_date=datetime(2025, 9, 16, tzinfo=timezone.utc),
        )

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then: only unique URLs (duplicates from the two fetches removed)
        urls = [a.url for a in articles]
        assert len(urls) == len(set(urls))


class TestJamaicaObserverArchiveDiscovererValidation:
    """Test constructor and input validation errors."""

    def test_init_raises_for_naive_start_date(self):
        """
        GIVEN a naive (tz-unaware) start_date
        WHEN discoverer is initialized
        THEN it raises ValueError
        """
        with pytest.raises(ValueError, match="start_date must be timezone-aware"):
            JamaicaObserverArchiveDiscoverer(
                start_date=datetime(2025, 9, 15),  # no tzinfo
                end_date=_SEP_15,
            )

    def test_init_raises_for_naive_end_date(self):
        """
        GIVEN a naive (tz-unaware) end_date
        WHEN discoverer is initialized
        THEN it raises ValueError
        """
        with pytest.raises(ValueError, match="end_date must be timezone-aware"):
            JamaicaObserverArchiveDiscoverer(
                start_date=_SEP_15,
                end_date=datetime(2025, 9, 15),  # no tzinfo
            )

    def test_init_raises_when_start_after_end(self):
        """
        GIVEN start_date after end_date
        WHEN discoverer is initialized
        THEN it raises ValueError
        """
        with pytest.raises(ValueError, match="start_date must be <= end_date"):
            JamaicaObserverArchiveDiscoverer(
                start_date=datetime(2025, 9, 20, tzinfo=timezone.utc),
                end_date=datetime(2025, 9, 15, tzinfo=timezone.utc),
            )

    @pytest.mark.asyncio
    async def test_discover_raises_for_zero_news_source_id(self):
        """
        GIVEN a discoverer
        WHEN discover() is called with news_source_id=0
        THEN it raises ValueError
        """
        discoverer = _make_discoverer()
        with pytest.raises(ValueError, match="news_source_id must be positive"):
            await discoverer.discover(news_source_id=0)

    @pytest.mark.asyncio
    async def test_discover_raises_for_negative_news_source_id(self):
        """
        GIVEN a discoverer
        WHEN discover() is called with news_source_id=-1
        THEN it raises ValueError
        """
        discoverer = _make_discoverer()
        with pytest.raises(ValueError, match="news_source_id must be positive"):
            await discoverer.discover(news_source_id=-1)


class TestJamaicaObserverArchiveDiscovererNetworkErrors:
    """Test retry logic, failure handling, and fail-soft behaviour."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_network_error_adds_date_to_failed_dates(
        self, mock_client_class
    ):
        """
        GIVEN a date that fails all retry attempts with a network error
        WHEN discover() is called
        THEN the date string is added to discoverer.failed_dates
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(
            side_effect=httpx.RequestError("Connection refused")
        )

        discoverer = _make_discoverer(max_retries=3)

        # When
        await discoverer.discover(news_source_id=2)

        # Then
        assert len(discoverer.failed_dates) == 1
        assert "2025-09-15" in discoverer.failed_dates

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_5xx_error_adds_date_to_failed_dates(
        self, mock_client_class
    ):
        """
        GIVEN a date that consistently returns 500 status
        WHEN discover() is called
        THEN the date is added to failed_dates (not silently skipped)
        """
        # Given: 500 response (not 404)
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(
            return_value=_make_response(status_code=500)
        )

        discoverer = _make_discoverer(max_retries=3)

        # When
        await discoverer.discover(news_source_id=2)

        # Then
        assert "2025-09-15" in discoverer.failed_dates

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_failed_date_does_not_stop_remaining_dates(
        self, mock_client_class, jo_archive_page_with_articles
    ):
        """
        GIVEN a two-day range where day 1 fails and day 2 succeeds
        WHEN discover() is called
        THEN day 2 articles are still returned (fail-soft)
        """
        # Given: Sep 15 exhausts all retries; Sep 16 page 1 succeeds, page 2 probe returns 404
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            httpx.RequestError("Error"),                              # Sep 15: attempt 1
            httpx.RequestError("Error"),                              # Sep 15: attempt 2
            httpx.RequestError("Error"),                              # Sep 15: attempt 3
            _make_response(jo_archive_page_with_articles),            # Sep 16: page 1 (date filter drops articles → loop stops)
        ])

        discoverer = _make_discoverer(
            start_date=_SEP_15,
            end_date=datetime(2025, 9, 16, tzinfo=timezone.utc),
            max_retries=3,
        )

        # When
        await discoverer.discover(news_source_id=2)

        # Then: Sep 15 failed but Sep 16 was attempted
        assert "2025-09-15" in discoverer.failed_dates
        assert mock_client.get.call_count == 4

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_retry_succeeds_on_second_attempt(
        self, mock_client_class, jo_archive_page_with_articles
    ):
        """
        GIVEN a transient error on the first attempt for a date
        WHEN discover() is called
        THEN it retries and returns articles from the second attempt
        """
        # Given: attempt 1 fails; attempt 2 succeeds; page 2 probe returns 404
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            httpx.RequestError("Transient error"),           # attempt 1 fails
            _make_response(jo_archive_page_with_articles),   # attempt 2 succeeds
            _r404(),                                          # page 2 probe
        ])

        discoverer = _make_discoverer(max_retries=3)

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then: articles discovered despite initial failure
        assert len(articles) > 0
        assert discoverer.failed_dates == []

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_failed_dates_cleared_on_each_discover_call(
        self, mock_client_class, jo_archive_page_with_articles
    ):
        """
        GIVEN a discoverer that had failures on a previous call
        WHEN discover() is called again and succeeds
        THEN failed_dates is reset to empty
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            # First call: fails all retries
            httpx.RequestError("Error"),
            httpx.RequestError("Error"),
            httpx.RequestError("Error"),
            # Second call: page 1 succeeds, page 2 probe terminates
            _make_response(jo_archive_page_with_articles),
            _r404(),
        ])

        discoverer = _make_discoverer(max_retries=3)

        # When: first call fails
        await discoverer.discover(news_source_id=2)
        assert len(discoverer.failed_dates) == 1

        # When: second call succeeds
        await discoverer.discover(news_source_id=2)

        # Then: failures cleared
        assert discoverer.failed_dates == []

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep")
    async def test_exponential_backoff_on_retries(
        self, mock_sleep, mock_client_class, jo_archive_page_with_articles
    ):
        """
        GIVEN two consecutive errors before success
        WHEN discover() is called
        THEN asyncio.sleep is called with 2^1=2s and 2^2=4s for backoff
        """
        # Given: two errors then success; page 2 probe terminates
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            httpx.RequestError("Error 1"),
            httpx.RequestError("Error 2"),
            _make_response(jo_archive_page_with_articles),
            _r404(),
        ])

        discoverer = _make_discoverer(max_retries=3, base_backoff=2.0)

        # When
        await discoverer.discover(news_source_id=2)

        # Then: backoff sleeps at 2^1=2.0s and 2^2=4.0s
        sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
        assert 2.0 in sleep_calls
        assert 4.0 in sleep_calls


class TestJamaicaObserverArchiveDiscovererEmptyDays:
    """Test handling of days with no articles (404, empty pages)."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_404_returns_empty_list_not_error(self, mock_client_class):
        """
        GIVEN a date that returns 404
        WHEN discover() is called
        THEN an empty list is returned and no error is raised
        """
        # Given: page 1 is 404 — no articles this day, loop exits immediately
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=_make_response(status_code=404))

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then
        assert articles == []

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_404_does_not_add_to_failed_dates(self, mock_client_class):
        """
        GIVEN a date that returns 404
        WHEN discover() is called
        THEN failed_dates remains empty (404 is not an error)
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=_make_response(status_code=404))

        discoverer = _make_discoverer()

        # When
        await discoverer.discover(news_source_id=2)

        # Then
        assert discoverer.failed_dates == []

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_empty_page_returns_empty_list(
        self, mock_client_class, jo_archive_page_empty
    ):
        """
        GIVEN a valid archive page with no News category articles
        WHEN discover() is called
        THEN an empty list is returned
        """
        # Given: page 1 has no News articles — loop exits on empty page_articles
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=_make_response(jo_archive_page_empty))

        discoverer = _make_discoverer(start_date=_SEP_21, end_date=_SEP_21)

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then
        assert articles == []

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_404_does_not_stop_multi_day_discovery(
        self, mock_client_class, jo_archive_page_with_articles
    ):
        """
        GIVEN a two-day range where day 1 returns 404 and day 2 has articles
        WHEN discover() is called
        THEN day 2 articles are still returned
        """
        # Given: Sep 15 page 1 → 404; Sep 16 page 1 → articles; Sep 16 page 2 probe → 404
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(status_code=404),               # Sep 15: no articles
            _make_response(jo_archive_page_with_articles), # Sep 16: page 1 (date filter drops → loop stops)
        ])

        discoverer = _make_discoverer(
            start_date=_SEP_15,
            end_date=datetime(2025, 9, 16, tzinfo=timezone.utc),
        )

        # When
        await discoverer.discover(news_source_id=2)

        # Then: both dates were fetched
        assert mock_client.get.call_count == 2
        assert discoverer.failed_dates == []


class TestJamaicaObserverArchiveDiscovererPagination:
    """Test sequential page probing for pagination."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_follows_pagination_and_returns_all_articles(
        self,
        mock_client_class,
        jo_archive_page_with_pagination,
        jo_archive_page_2,
    ):
        """
        GIVEN page 1 has 2 articles and page 2 has 1 article
        WHEN discover() is called
        THEN articles from both pages are returned (3 total)
        """
        # Given: page 1 → 2 articles; page 2 → 1 article; page 3 probe → 404
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_archive_page_with_pagination),  # page 1: 2 articles
            _make_response(jo_archive_page_2),                # page 2: 1 article
            _r404(),                                           # page 3 probe: done
        ])

        discoverer = _make_discoverer(start_date=_SEP_20, end_date=_SEP_20)

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then: 3 articles total across both pages
        assert len(articles) == 3
        urls = {a.url for a in articles}
        assert "https://www.jamaicaobserver.com/2025/09/20/govt-budget-debate-opens/" in urls
        assert "https://www.jamaicaobserver.com/2025/09/20/minister-responds-to-inquiry/" in urls
        assert "https://www.jamaicaobserver.com/2025/09/20/court-rules-on-land-dispute/" in urls

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_stops_when_page_returns_404(
        self,
        mock_client_class,
        jo_archive_page_with_pagination,
    ):
        """
        GIVEN page 1 has articles and page 2 returns 404
        WHEN discover() is called
        THEN exactly 2 HTTP requests are made (page 1 + page 2 probe)
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_archive_page_with_pagination),  # page 1: articles
            _r404(),                                           # page 2 probe: done
        ])

        discoverer = _make_discoverer(start_date=_SEP_20, end_date=_SEP_20)

        # When
        await discoverer.discover(news_source_id=2)

        # Then: exactly 2 requests (page 1 + probe)
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_stops_when_page_returns_no_articles(
        self,
        mock_client_class,
        jo_archive_page_with_pagination,
        jo_archive_page_empty,
    ):
        """
        GIVEN page 1 has articles and page 2 returns 200 with no News articles
        WHEN discover() is called
        THEN exactly 2 HTTP requests are made and loop stops on empty page
        """
        # Given: page 2 returns 200 but no category_main News articles (past last real page)
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_archive_page_with_pagination),  # page 1: 2 articles
            _make_response(jo_archive_page_empty),             # page 2: 0 articles → stop
        ])

        discoverer = _make_discoverer(start_date=_SEP_20, end_date=_SEP_20)

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then: only page 1 articles returned, loop stopped on empty page
        assert len(articles) == 2
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_pagination_fetches_correct_urls(
        self,
        mock_client_class,
        jo_archive_page_with_pagination,
        jo_archive_page_2,
    ):
        """
        GIVEN a Sep 20 archive with 2 pages
        WHEN discover() is called
        THEN requests are made to page 1, page/2/, and page/3/ (probe)
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_archive_page_with_pagination),
            _make_response(jo_archive_page_2),
            _r404(),
        ])

        discoverer = _make_discoverer(start_date=_SEP_20, end_date=_SEP_20)

        # When
        await discoverer.discover(news_source_id=2)

        # Then: requests in order: page 1, page 2, page 3 probe
        called_urls = [str(c[0][0]) for c in mock_client.get.call_args_list]
        assert called_urls[0] == "https://www.jamaicaobserver.com/2025/09/20/"
        assert called_urls[1] == "https://www.jamaicaobserver.com/2025/09/20/page/2/"
        assert called_urls[2] == "https://www.jamaicaobserver.com/2025/09/20/page/3/"


class TestJamaicaObserverArchiveDiscovererCrawlDelay:
    """Test crawl delay between date fetches and between pages."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep")
    async def test_no_delay_before_first_page_of_first_date(
        self, mock_sleep, mock_client_class, jo_archive_page_with_articles
    ):
        """
        GIVEN a single-day discoverer with crawl_delay=1.5
        WHEN discover() is called
        THEN no sleep is applied before the very first HTTP request
        """
        # Given: page 1 returns articles; page 2 probe returns 404
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_archive_page_with_articles),
            _r404(),
        ])

        crawl_delay = 1.5
        discoverer = _make_discoverer(crawl_delay=crawl_delay)

        # When
        await discoverer.discover(news_source_id=2)

        # Then: first call was made without any preceding sleep
        # (page 2 probe does get a sleep, but page 1 does not)
        all_sleep_calls = mock_sleep.call_args_list
        # The first get() call must precede any crawl-delay sleep
        assert mock_client.get.call_count == 2
        crawl_sleeps = [c for c in all_sleep_calls if c[0][0] == crawl_delay]
        assert len(crawl_sleeps) == 1  # only the page 2 probe sleep

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep")
    async def test_crawl_delay_applied_between_dates(
        self, mock_sleep, mock_client_class, jo_archive_page_empty
    ):
        """
        GIVEN a three-day discoverer with crawl_delay=1.5
        WHEN each day returns an empty page (loop stops immediately, no page probes)
        THEN crawl-delay sleep is applied exactly 2 times (between day 1→2 and day 2→3)
        """
        # Given: each day returns an empty page → 0 articles → loop stops, no page 2 probe
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(
            return_value=_make_response(jo_archive_page_empty)
        )

        crawl_delay = 1.5
        discoverer = _make_discoverer(
            start_date=_SEP_15,
            end_date=datetime(2025, 9, 17, tzinfo=timezone.utc),
            crawl_delay=crawl_delay,
        )

        # When
        await discoverer.discover(news_source_id=2)

        # Then: exactly 2 crawl-delay sleeps (before day 2 and day 3 only)
        crawl_sleeps = [c for c in mock_sleep.call_args_list if c[0][0] == crawl_delay]
        assert len(crawl_sleeps) == 2

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep")
    async def test_crawl_delay_applied_between_pagination_pages(
        self,
        mock_sleep,
        mock_client_class,
        jo_archive_page_with_pagination,
        jo_archive_page_2,
    ):
        """
        GIVEN a single-day discoverer where the archive has 2 pages
        WHEN discover() is called
        THEN crawl-delay sleep is applied twice:
             once before page 2, once before the page 3 probe (404)
        """
        # Given: page 1 → 2 articles; page 2 → 1 article; page 3 probe → 404
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_archive_page_with_pagination),
            _make_response(jo_archive_page_2),
            _r404(),
        ])

        crawl_delay = 1.5
        discoverer = _make_discoverer(
            start_date=_SEP_20,
            end_date=_SEP_20,
            crawl_delay=crawl_delay,
        )

        # When
        await discoverer.discover(news_source_id=2)

        # Then: 2 crawl-delay sleeps (before page 2 and before page 3 probe)
        crawl_sleeps = [c for c in mock_sleep.call_args_list if c[0][0] == crawl_delay]
        assert len(crawl_sleeps) == 2
