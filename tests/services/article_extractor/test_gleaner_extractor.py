"""Tests for GleanerExtractor strategy."""
import pytest
from datetime import datetime, timezone

from src.services.article_extractor.gleaner_extractor import GleanerExtractor
from src.services.article_extractor.models import ExtractedArticleContent


class TestGleanerExtractorHappyPath:
    """Happy path tests for Gleaner extraction."""

    async def test_extract_complete_article(self, gleaner_html: str):
        # Given: valid Gleaner article HTML with all elements
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/20251118/court-rejects-claims-nullity-reid-cmu-fraud-case-trial-proceed"

        # When: extracting content
        content = extractor.extract(gleaner_html, url)

        # Then: all fields are extracted correctly
        assert isinstance(content, ExtractedArticleContent)
        assert content.title == "Court rejects claims of nullity in Reid-CMU fraud case; trial to proceed"
        assert content.full_text is not None
        assert len(content.full_text) >= 50
        assert "Senior Parish Judge Sanchia Burrell" in content.full_text
        assert content.author == "Tanesha Mundle"
        assert content.published_date is not None
        assert content.published_date.year == 2025
        assert content.published_date.month == 11
        assert content.published_date.day == 18

    async def test_author_name_cleaned(self, gleaner_html: str):
        # Given: Gleaner article HTML with author in format "Name/Staff Reporter"
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(gleaner_html, url)

        # Then: "/Staff Reporter" suffix is removed from author name
        assert content.author == "Tanesha Mundle"
        assert "/Staff Reporter" not in content.author

    async def test_published_date_is_timezone_aware(self, gleaner_html: str):
        # Given: Gleaner article HTML with ISO 8601 date
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(gleaner_html, url)

        # Then: published_date is timezone-aware (UTC)
        assert content.published_date is not None
        assert content.published_date.tzinfo is not None
        assert content.published_date.tzinfo == timezone.utc


class TestGleanerExtractorParsingErrors:
    """Parsing error tests for Gleaner extraction."""

    async def test_missing_title_raises_value_error(self):
        # Given: HTML without title element
        html = "<html><body><div class='article-content'><p>Content without title</p></div></body></html>"
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When/Then: extraction raises ValueError
        with pytest.raises(ValueError) as exc_info:
            extractor.extract(html, url)

        assert "Could not extract title" in str(exc_info.value)
        assert url in str(exc_info.value)

    async def test_missing_content_raises_value_error(self):
        # Given: HTML without article content container
        html = "<html><body><h1 class='title'>Title Only</h1></body></html>"
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When/Then: extraction raises ValueError
        with pytest.raises(ValueError) as exc_info:
            extractor.extract(html, url)

        assert "content container" in str(exc_info.value).lower()
        assert url in str(exc_info.value)

    async def test_empty_content_div_raises_value_error(self):
        # Given: HTML with content container but no paragraphs
        html = """
        <html>
            <body>
                <h1 class="title">Test Title</h1>
                <div class="article-content">
                    <div>Some div content but no paragraphs</div>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When/Then: extraction raises ValueError
        with pytest.raises(ValueError) as exc_info:
            extractor.extract(html, url)

        assert "paragraphs" in str(exc_info.value).lower()

    async def test_too_short_text_raises_value_error(self):
        # Given: HTML with very short article text (less than 50 chars)
        html = """
        <html>
            <body>
                <h1 class="title">Test Title</h1>
                <div class="article-content">
                    <p>Short.</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When/Then: extraction raises ValueError
        with pytest.raises(ValueError) as exc_info:
            extractor.extract(html, url)

        assert "too short" in str(exc_info.value).lower()


class TestGleanerExtractorEdgeCases:
    """Edge case tests for Gleaner extraction."""

    async def test_missing_author_returns_none(self):
        # Given: HTML without author element
        html = """
        <html>
            <body>
                <h1 class="title">Test Article Title</h1>
                <div class="article-content">
                    <p>This is a test article with sufficient length to pass validation requirements.</p>
                    <p>It has multiple paragraphs to ensure proper extraction.</p>
                </div>
                <meta property="article:published_time" content="2025-11-18T00:09:18-05:00">
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: extraction succeeds with author=None
        assert content.title is not None
        assert content.full_text is not None
        assert content.author is None

    async def test_missing_date_returns_none(self):
        # Given: HTML without date meta tag
        html = """
        <html>
            <body>
                <h1 class="title">Test Article Title</h1>
                <div class="article-content">
                    <p>This is a test article with sufficient length to pass validation requirements.</p>
                    <p>It has multiple paragraphs to ensure proper extraction.</p>
                </div>
                <a class="author-term">John Doe/Staff Reporter</a>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: extraction succeeds with published_date=None
        assert content.title is not None
        assert content.full_text is not None
        assert content.published_date is None

    async def test_fallback_to_field_name_body(self):
        # Given: HTML with field-name-body instead of article-content
        html = """
        <html>
            <body>
                <h1 class="title">Test Article Title</h1>
                <div class="field-name-body">
                    <p>This is a test article using the field-name-body container class.</p>
                    <p>It should still be extracted successfully as a fallback option.</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: extraction succeeds using fallback container
        assert content.title == "Test Article Title"
        assert "field-name-body container" in content.full_text

    async def test_fallback_to_generic_h1(self):
        # Given: HTML with h1 but without class="title"
        html = """
        <html>
            <body>
                <h1>Generic H1 Title</h1>
                <div class="article-content">
                    <p>This is a test article with an h1 tag that doesn't have the title class.</p>
                    <p>The extractor should still find it as a fallback option for title extraction.</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: extraction succeeds using fallback h1
        assert content.title == "Generic H1 Title"
