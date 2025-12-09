"""Tests for article discovery models."""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from src.article_discovery.models import DiscoveredArticle


class TestDiscoveredArticleValidation:
    """Validation tests for DiscoveredArticle model."""

    # URL validation tests

    async def test_empty_url_raises_value_error(self):
        # Given: a DiscoveredArticle with empty URL
        # When: creation is attempted
        # Then: raises ValueError with message about URL
        with pytest.raises(ValueError, match="URL cannot be empty"):
            DiscoveredArticle(
                url="",
                news_source_id=1,
                section="news",
                discovered_at=datetime.now(timezone.utc),
            )

    async def test_whitespace_only_url_raises_value_error(self):
        # Given: a DiscoveredArticle with whitespace-only URL
        # When: creation is attempted
        # Then: raises ValueError with message about URL
        with pytest.raises(ValueError, match="URL cannot be empty"):
            DiscoveredArticle(
                url="   ",
                news_source_id=1,
                section="news",
                discovered_at=datetime.now(timezone.utc),
            )

    async def test_url_without_protocol_raises_value_error(self):
        # Given: a DiscoveredArticle with URL missing http:// or https://
        # When: creation is attempted
        # Then: raises ValueError with message about URL protocol
        with pytest.raises(
            ValueError, match="URL must start with http:// or https://"
        ):
            DiscoveredArticle(
                url="jamaica-gleaner.com/article",
                news_source_id=1,
                section="news",
                discovered_at=datetime.now(timezone.utc),
            )

    async def test_url_with_leading_trailing_whitespace_is_stripped(self):
        # Given: a DiscoveredArticle with URL having leading/trailing whitespace
        # When: creation is attempted
        # Then: whitespace is stripped and URL is valid
        article = DiscoveredArticle(
            url="  https://jamaica-gleaner.com/article  ",
            news_source_id=1,
            section="news",
            discovered_at=datetime.now(timezone.utc),
        )
        assert article.url == "https://jamaica-gleaner.com/article"

    async def test_valid_url_with_https_succeeds(self):
        # Given: a DiscoveredArticle with valid HTTPS URL
        # When: creation is attempted
        # Then: DiscoveredArticle is created successfully
        article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article/news/20240101/test",
            news_source_id=1,
            section="news",
            discovered_at=datetime.now(timezone.utc),
        )
        assert article.url == "https://jamaica-gleaner.com/article/news/20240101/test"

    async def test_valid_url_with_http_succeeds(self):
        # Given: a DiscoveredArticle with valid HTTP URL
        # When: creation is attempted
        # Then: DiscoveredArticle is created successfully
        article = DiscoveredArticle(
            url="http://jamaica-gleaner.com/article/news/20240101/test",
            news_source_id=1,
            section="news",
            discovered_at=datetime.now(timezone.utc),
        )
        assert article.url == "http://jamaica-gleaner.com/article/news/20240101/test"

    # Section validation tests

    async def test_empty_section_raises_value_error(self):
        # Given: a DiscoveredArticle with empty section
        # When: creation is attempted
        # Then: raises ValueError with message about empty section
        with pytest.raises(ValueError, match="Section cannot be empty"):
            DiscoveredArticle(
                url="https://jamaica-gleaner.com/article",
                news_source_id=1,
                section="",
                discovered_at=datetime.now(timezone.utc),
            )

    async def test_whitespace_only_section_raises_value_error(self):
        # Given: a DiscoveredArticle with whitespace-only section
        # When: creation is attempted
        # Then: raises ValueError with message about empty section
        with pytest.raises(ValueError, match="Section cannot be empty"):
            DiscoveredArticle(
                url="https://jamaica-gleaner.com/article",
                news_source_id=1,
                section="   ",
                discovered_at=datetime.now(timezone.utc),
            )

    async def test_section_with_leading_trailing_whitespace_is_stripped(self):
        # Given: a DiscoveredArticle with section having leading/trailing whitespace
        # When: creation is attempted
        # Then: whitespace is stripped and section is valid
        article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article",
            news_source_id=1,
            section="  lead-stories  ",
            discovered_at=datetime.now(timezone.utc),
        )
        assert article.section == "lead-stories"

    async def test_valid_section_succeeds(self):
        # Given: a DiscoveredArticle with valid section
        # When: creation is attempted
        # Then: DiscoveredArticle is created successfully
        article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article",
            news_source_id=1,
            section="opinion",
            discovered_at=datetime.now(timezone.utc),
        )
        assert article.section == "opinion"

    # news_source_id validation tests

    async def test_zero_news_source_id_raises_value_error(self):
        # Given: a DiscoveredArticle with news_source_id of zero
        # When: creation is attempted
        # Then: raises ValueError with message about positive ID
        with pytest.raises(ValueError, match="News source ID must be positive"):
            DiscoveredArticle(
                url="https://jamaica-gleaner.com/article",
                news_source_id=0,
                section="news",
                discovered_at=datetime.now(timezone.utc),
            )

    async def test_negative_news_source_id_raises_value_error(self):
        # Given: a DiscoveredArticle with negative news_source_id
        # When: creation is attempted
        # Then: raises ValueError with message about positive ID
        with pytest.raises(ValueError, match="News source ID must be positive"):
            DiscoveredArticle(
                url="https://jamaica-gleaner.com/article",
                news_source_id=-1,
                section="news",
                discovered_at=datetime.now(timezone.utc),
            )

    async def test_valid_news_source_id_succeeds(self):
        # Given: a DiscoveredArticle with valid positive news_source_id
        # When: creation is attempted
        # Then: DiscoveredArticle is created successfully
        article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article",
            news_source_id=1,
            section="news",
            discovered_at=datetime.now(timezone.utc),
        )
        assert article.news_source_id == 1

    # discovered_at validation tests

    async def test_naive_discovered_at_raises_value_error(self):
        # Given: a DiscoveredArticle with timezone-naive discovered_at
        # When: creation is attempted
        # Then: raises ValueError with message about timezone awareness
        with pytest.raises(ValueError, match="Discovered timestamp must be timezone-aware"):
            DiscoveredArticle(
                url="https://jamaica-gleaner.com/article",
                news_source_id=1,
                section="news",
                discovered_at=datetime(2024, 1, 1, 12, 0, 0),  # naive datetime
            )

    async def test_timezone_aware_discovered_at_succeeds(self):
        # Given: a DiscoveredArticle with timezone-aware discovered_at
        # When: creation is attempted
        # Then: DiscoveredArticle is created successfully
        now = datetime.now(timezone.utc)
        article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article",
            news_source_id=1,
            section="news",
            discovered_at=now,
        )
        assert article.discovered_at == now

    # title validation tests (optional field)

    async def test_none_title_succeeds(self):
        # Given: a DiscoveredArticle with None title
        # When: creation is attempted
        # Then: DiscoveredArticle is created successfully with title as None
        article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article",
            news_source_id=1,
            section="news",
            discovered_at=datetime.now(timezone.utc),
            title=None,
        )
        assert article.title is None

    async def test_empty_string_title_becomes_none(self):
        # Given: a DiscoveredArticle with empty string title
        # When: creation is attempted
        # Then: title is normalized to None
        article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article",
            news_source_id=1,
            section="news",
            discovered_at=datetime.now(timezone.utc),
            title="",
        )
        assert article.title is None

    async def test_whitespace_only_title_becomes_none(self):
        # Given: a DiscoveredArticle with whitespace-only title
        # When: creation is attempted
        # Then: title is normalized to None
        article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article",
            news_source_id=1,
            section="news",
            discovered_at=datetime.now(timezone.utc),
            title="   ",
        )
        assert article.title is None

    async def test_title_with_leading_trailing_whitespace_is_stripped(self):
        # Given: a DiscoveredArticle with title having leading/trailing whitespace
        # When: creation is attempted
        # Then: whitespace is stripped and title is valid
        article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article",
            news_source_id=1,
            section="news",
            discovered_at=datetime.now(timezone.utc),
            title="  Government Announces New Policy  ",
        )
        assert article.title == "Government Announces New Policy"

    async def test_valid_title_succeeds(self):
        # Given: a DiscoveredArticle with valid title
        # When: creation is attempted
        # Then: DiscoveredArticle is created successfully
        article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article",
            news_source_id=1,
            section="news",
            discovered_at=datetime.now(timezone.utc),
            title="Government Announces New Transparency Measures",
        )
        assert article.title == "Government Announces New Transparency Measures"

    # published_date validation tests (optional field)

    async def test_none_published_date_succeeds(self):
        # Given: a DiscoveredArticle with None published_date
        # When: creation is attempted
        # Then: DiscoveredArticle is created successfully with published_date as None
        article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article",
            news_source_id=1,
            section="news",
            discovered_at=datetime.now(timezone.utc),
            published_date=None,
        )
        assert article.published_date is None

    async def test_naive_published_date_raises_value_error(self):
        # Given: a DiscoveredArticle with timezone-naive published_date
        # When: creation is attempted
        # Then: raises ValueError with message about timezone awareness
        with pytest.raises(ValueError, match="Published date must be timezone-aware"):
            DiscoveredArticle(
                url="https://jamaica-gleaner.com/article",
                news_source_id=1,
                section="news",
                discovered_at=datetime.now(timezone.utc),
                published_date=datetime(2024, 1, 1, 12, 0, 0),  # naive datetime
            )

    async def test_timezone_aware_published_date_succeeds(self):
        # Given: a DiscoveredArticle with timezone-aware published_date
        # When: creation is attempted
        # Then: DiscoveredArticle is created successfully
        published = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article",
            news_source_id=1,
            section="news",
            discovered_at=datetime.now(timezone.utc),
            published_date=published,
        )
        assert article.published_date == published


class TestDiscoveredArticleHappyPath:
    """Happy path tests for DiscoveredArticle model."""

    async def test_minimal_required_fields_succeeds(self):
        # Given: a DiscoveredArticle with only required fields
        # When: creation is attempted
        # Then: DiscoveredArticle is created successfully
        now = datetime.now(timezone.utc)
        article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article/news/20240101/test",
            news_source_id=1,
            section="news",
            discovered_at=now,
        )
        assert article.url == "https://jamaica-gleaner.com/article/news/20240101/test"
        assert article.news_source_id == 1
        assert article.section == "news"
        assert article.discovered_at == now
        assert article.title is None
        assert article.published_date is None

    async def test_all_fields_populated_succeeds(self):
        # Given: a DiscoveredArticle with all fields populated
        # When: creation is attempted
        # Then: DiscoveredArticle is created successfully with all fields
        discovered = datetime.now(timezone.utc)
        published = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article/news/20240101/test",
            news_source_id=1,
            section="news",
            discovered_at=discovered,
            title="Breaking: Government Announces New Policy",
            published_date=published,
        )
        assert article.url == "https://jamaica-gleaner.com/article/news/20240101/test"
        assert article.news_source_id == 1
        assert article.section == "news"
        assert article.discovered_at == discovered
        assert article.title == "Breaking: Government Announces New Policy"
        assert article.published_date == published

    async def test_multiple_sections_succeeds(self):
        # Given: DiscoveredArticles from different sections
        # When: creation is attempted
        # Then: all are created successfully with their respective sections
        now = datetime.now(timezone.utc)

        news_article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article/news/1",
            news_source_id=1,
            section="news",
            discovered_at=now,
        )

        opinion_article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article/opinion/2",
            news_source_id=1,
            section="opinion",
            discovered_at=now,
        )

        sports_article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article/sports/3",
            news_source_id=1,
            section="sports",
            discovered_at=now,
        )

        assert news_article.section == "news"
        assert opinion_article.section == "opinion"
        assert sports_article.section == "sports"

    async def test_unicode_title_succeeds(self):
        # Given: a DiscoveredArticle with Unicode characters in title
        # When: creation is attempted
        # Then: DiscoveredArticle is created successfully with Unicode title
        title_text = "Minister's Statement on Accountability Initiative"
        article = DiscoveredArticle(
            url="https://jamaica-gleaner.com/article",
            news_source_id=1,
            section="news",
            discovered_at=datetime.now(timezone.utc),
            title=title_text,
        )
        assert article.title == title_text

    async def test_very_long_url_succeeds(self):
        # Given: a DiscoveredArticle with very long URL
        # When: creation is attempted
        # Then: DiscoveredArticle is created successfully
        long_url = f"https://jamaica-gleaner.com/article/{'a' * 500}/test"
        article = DiscoveredArticle(
            url=long_url,
            news_source_id=1,
            section="news",
            discovered_at=datetime.now(timezone.utc),
        )
        assert article.url == long_url
