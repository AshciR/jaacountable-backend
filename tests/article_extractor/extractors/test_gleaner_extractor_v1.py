"""Tests for GleanerExtractorV1 (CSS-only strategy)."""
import pytest
from datetime import timezone

from src.article_extractor.extractors.gleaner_extractor_v1 import GleanerExtractorV1
from src.article_extractor.models import ExtractedArticleContent


class TestGleanerExtractorV1HappyPath:
    """Happy path tests for V1 CSS-only extraction."""

    async def test_extract_complete_article_from_v1_html(self, gleaner_html_v1: str):
        # Given: valid Gleaner article HTML with legacy CSS structure
        extractor = GleanerExtractorV1()
        url = "https://jamaica-gleaner.com/article/news/20251118/court-rejects-claims-nullity-reid-cmu-fraud-case-trial-proceed"

        # When: extracting content
        content = extractor.extract(gleaner_html_v1, url)

        # Then: all fields are extracted correctly using CSS-only selectors
        assert isinstance(content, ExtractedArticleContent)

        # Title from h1.title
        assert content.title == "Court rejects claims of nullity in Reid-CMU fraud case; trial to proceed"

        # Full text from div.article-content (verify it starts with expected text)
        assert content.full_text is not None
        assert content.full_text.startswith("Senior Parish Judge Sanchia Burrell yesterday cleared the way for the continuation of the long-runni")

        # Author from a.author-term (cleaned)
        assert content.author == "Tanesha Mundle"

        # Published date from meta[property="article:published_time"] (converted to UTC)
        assert content.published_date is not None
        assert content.published_date.year == 2025
        assert content.published_date.month == 11
        assert content.published_date.day == 18
        assert content.published_date.tzinfo == timezone.utc

    async def test_extract_with_legacy_css_selectors(self):
        # Given: HTML with legacy CSS classes (h1.title, div.article-content)
        html = """
        <html>
            <body>
                <h1 class="title">V1 Legacy Title</h1>
                <div class="article-content">
                    <p>V1 content paragraph with enough text to pass validation requirements for extraction.</p>
                    <p>Second paragraph of V1 content that adds more length to the article.</p>
                </div>
                <a class="author-term">V1 Author/Staff Reporter</a>
                <meta property="article:published_time" content="2025-12-10T12:00:00-05:00">
            </body>
        </html>
        """
        extractor = GleanerExtractorV1()
        url = "https://jamaica-gleaner.com/article/news/legacy"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: extraction succeeds using V1 CSS selectors
        assert content.title == "V1 Legacy Title"
        assert content.full_text.startswith("V1 content paragraph")
        assert "Second paragraph" in content.full_text
        assert content.author == "V1 Author"
        assert content.published_date is not None
        assert content.published_date.year == 2025
        assert content.published_date.tzinfo == timezone.utc

    async def test_extract_with_older_legacy_selectors(self):
        # Given: HTML with older legacy classes (div.field-name-body)
        html = """
        <html>
            <body>
                <h1>Fallback H1 Title</h1>
                <div class="field-name-body">
                    <p>Older legacy content with sufficient length for validation requirements.</p>
                    <p>Additional paragraph to ensure content meets minimum length.</p>
                </div>
                <time datetime="2025-12-10T10:00:00-05:00">Dec 10, 2025</time>
            </body>
        </html>
        """
        extractor = GleanerExtractorV1()
        url = "https://jamaica-gleaner.com/article/news/older-legacy"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: extraction succeeds using older fallback selectors
        assert content.title == "Fallback H1 Title"
        assert content.full_text.startswith("Older legacy content")
        assert content.published_date is not None

    async def test_extract_filters_email_paragraphs(self):
        # Given: HTML with email paragraph (common in Gleaner articles)
        html = """
        <html>
            <body>
                <h1 class="title">Article Title</h1>
                <div class="article-content">
                    <p>First paragraph of actual content that is long enough to pass validation.</p>
                    <p>Second paragraph with more real content for the article.</p>
                    <p>reporter.email@gleanerjm.com</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractorV1()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: email paragraph is filtered out
        assert "@gleanerjm.com" not in content.full_text
        assert "First paragraph" in content.full_text
        assert "Second paragraph" in content.full_text

    async def test_author_cleaning_removes_staff_reporter(self):
        # Given: HTML with author in "Name/Staff Reporter" format
        html = """
        <html>
            <body>
                <h1 class="title">Test Article</h1>
                <div class="article-content">
                    <p>Content paragraph that is long enough to pass validation requirements.</p>
                </div>
                <a class="author-term">John Smith/Staff Reporter</a>
            </body>
        </html>
        """
        extractor = GleanerExtractorV1()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: "/Staff Reporter" suffix is removed
        assert content.author == "John Smith"
        assert "/Staff Reporter" not in content.author

    async def test_date_parsing_converts_to_utc(self):
        # Given: HTML with EST datetime (Jamaica timezone)
        html = """
        <html>
            <body>
                <h1 class="title">Date Test Article</h1>
                <div class="article-content">
                    <p>Content paragraph with enough length to pass validation requirements.</p>
                </div>
                <meta property="article:published_time" content="2025-12-10T15:30:00-05:00">
            </body>
        </html>
        """
        extractor = GleanerExtractorV1()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: date is converted to UTC and timezone-aware
        assert content.published_date is not None
        assert content.published_date.tzinfo == timezone.utc
        # EST -5 hours → UTC should be 20:30 UTC
        assert content.published_date.hour == 20
        assert content.published_date.minute == 30


class TestGleanerExtractorV1ParsingErrors:
    """V1 parsing error tests."""

    async def test_missing_title_raises_value_error(self):
        # Given: HTML without title
        html = """
        <html>
            <body>
                <div class="article-content">
                    <p>Content without title should fail extraction.</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractorV1()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When/Then: extraction raises ValueError
        with pytest.raises(ValueError) as exc_info:
            extractor.extract(html, url)

        assert "Could not extract title" in str(exc_info.value)
        assert url in str(exc_info.value)

    async def test_missing_content_container_raises_value_error(self):
        # Given: HTML without content container
        html = """
        <html>
            <body>
                <h1 class="title">Title Only</h1>
            </body>
        </html>
        """
        extractor = GleanerExtractorV1()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When/Then: extraction raises ValueError
        with pytest.raises(ValueError) as exc_info:
            extractor.extract(html, url)

        assert "content container" in str(exc_info.value).lower()
        assert url in str(exc_info.value)

    async def test_empty_content_raises_value_error(self):
        # Given: HTML with content container but no paragraphs
        html = """
        <html>
            <body>
                <h1 class="title">Title</h1>
                <div class="article-content">
                    <div>Not a paragraph</div>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractorV1()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When/Then: extraction raises ValueError
        with pytest.raises(ValueError) as exc_info:
            extractor.extract(html, url)

        assert "No paragraphs found" in str(exc_info.value)

    async def test_content_too_short_raises_value_error(self):
        # Given: HTML with very short content (less than 50 chars)
        html = """
        <html>
            <body>
                <h1 class="title">Title</h1>
                <div class="article-content">
                    <p>Too short</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractorV1()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When/Then: extraction raises ValueError
        with pytest.raises(ValueError) as exc_info:
            extractor.extract(html, url)

        assert "too short" in str(exc_info.value).lower()


class TestGleanerExtractorV1OptionalFields:
    """Tests for V1 optional fields (author, date)."""

    async def test_missing_author_returns_none(self):
        # Given: HTML without author
        html = """
        <html>
            <body>
                <h1 class="title">No Author Article</h1>
                <div class="article-content">
                    <p>Content paragraph with enough length to pass validation requirements.</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractorV1()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: author is None (optional field)
        assert content.author is None

    async def test_missing_date_returns_none(self):
        # Given: HTML without published date
        html = """
        <html>
            <body>
                <h1 class="title">No Date Article</h1>
                <div class="article-content">
                    <p>Content paragraph with enough length to pass validation requirements.</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractorV1()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: published_date is None (optional field)
        assert content.published_date is None

    async def test_invalid_date_format_returns_none(self):
        # Given: HTML with invalid date format
        html = """
        <html>
            <body>
                <h1 class="title">Invalid Date Article</h1>
                <div class="article-content">
                    <p>Content paragraph with enough length to pass validation requirements.</p>
                </div>
                <meta property="article:published_time" content="invalid-date-format">
            </body>
        </html>
        """
        extractor = GleanerExtractorV1()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: published_date is None (parsing failed gracefully)
        assert content.published_date is None
