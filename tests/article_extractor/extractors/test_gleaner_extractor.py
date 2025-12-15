"""Tests for GleanerExtractor wrapper with V2→V1 fallback."""
import pytest
from unittest.mock import patch
from datetime import timezone

from src.article_extractor.extractors.gleaner_extractor import GleanerExtractor


class TestGleanerExtractorFallbackLogic:
    """Tests for wrapper's V2→V1 fallback behavior."""

    async def test_v2_success_returns_content(self, gleaner_html_v2: str):
        # Given: Valid HTML that V2 can extract
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/20251210/embrace-one-health"

        # When: extracting content
        content = extractor.extract(gleaner_html_v2, url)

        # Then: V2 succeeds and returns content
        assert content.title == "Embrace \u2018One Health\u2019"
        assert content.author == "Corey Robinson"
        assert content.full_text is not None
        assert content.full_text.startswith("Medical experts are calling")

    async def test_v1_html_extraction_succeeds(self, gleaner_html_v1: str):
        # Given: HTML from V1 era (may work with V2 or fall back to V1)
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/20251118/court-rejects-claims-nullity-reid-cmu-fraud-case-trial-proceed"

        # When: extracting content
        content = extractor.extract(gleaner_html_v1, url)

        # Then: extraction succeeds (either V2 or V1)
        assert content.title == "Court rejects claims of nullity in Reid-CMU fraud case; trial to proceed"
        assert content.author == "Tanesha Mundle"
        assert content.full_text is not None

    async def test_legacy_css_only_html_extraction_succeeds(self):
        # Given: HTML with only legacy CSS classes (no JSON-LD, no new classes)
        # V2 will fail on new selectors, but fall back to legacy CSS
        # V1 will succeed immediately with legacy CSS
        html = """
        <html>
            <body>
                <h1 class="title">Legacy Title</h1>
                <div class="article-content">
                    <p>Legacy content that should be extracted with sufficient length for validation.</p>
                </div>
                <a class="author-term">Legacy Author</a>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/legacy"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: extraction succeeds
        assert content.title == "Legacy Title"
        assert content.author == "Legacy Author"
        assert content.full_text.startswith("Legacy content")

    async def test_both_fail_raises_combined_error(self):
        # Given: HTML that both extractors fail on
        html = """
        <html>
            <body>
                <div>No extractable content at all</div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/broken"

        # When/Then: both fail, combined error raised
        with pytest.raises(ValueError) as exc_info:
            extractor.extract(html, url)

        # Then: error contains information about all failures
        error_msg = str(exc_info.value)
        assert "All extractors failed" in error_msg
        assert "v2" in error_msg.lower()
        assert "v1" in error_msg.lower()


class TestGleanerExtractorBackwardCompatibility:
    """Tests that wrapper maintains existing behavior."""

    async def test_v2_html_extraction_works(self, gleaner_html_v2: str):
        # Given: V2 HTML fixture
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/20251210/embrace-one-health"

        # When: extracting content
        content = extractor.extract(gleaner_html_v2, url)

        # Then: extraction succeeds with expected values
        assert content.title == "Embrace \u2018One Health\u2019"
        assert content.author == "Corey Robinson"
        assert content.published_date is not None
        assert content.published_date.tzinfo == timezone.utc

    async def test_v1_html_extraction_works(self, gleaner_html_v1: str):
        # Given: V1 HTML fixture
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/20251118/court-rejects-claims-nullity-reid-cmu-fraud-case-trial-proceed"

        # When: extracting content
        content = extractor.extract(gleaner_html_v1, url)

        # Then: extraction succeeds (via V2 or V1)
        assert content.title == "Court rejects claims of nullity in Reid-CMU fraud case; trial to proceed"
        assert content.author == "Tanesha Mundle"
        assert content.published_date is not None
        assert content.published_date.tzinfo == timezone.utc


class TestGleanerExtractorEdgeCases:
    """Edge case tests for wrapper."""

    async def test_v2_succeeds_v1_not_attempted(self, gleaner_html_v2: str):
        # Given: HTML that V2 can extract successfully
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/20251210/embrace-one-health"

        # When: extracting content
        # V2 succeeds, so V1 should never be called
        with patch.object(extractor.v1_extractor, 'extract') as mock_v1:
            content = extractor.extract(gleaner_html_v2, url)

        # Then: V1 was never called (early return on V2 success)
        mock_v1.assert_not_called()
        assert content.title == "Embrace \u2018One Health\u2019"

    async def test_raises_value_error_only(self):
        # Given: HTML that causes ValueError
        html = """
        <html>
            <body>
                <h1 class="title">Title Only</h1>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When/Then: raises ValueError (not other exception types)
        with pytest.raises(ValueError):
            extractor.extract(html, url)

    async def test_v2_new_css_selectors_work(self):
        # Given: HTML with new V2 CSS selectors
        html = """
        <html>
            <body>
                <h1 class="article--title">New CSS Title</h1>
                <div class="article--body">
                    <p>Content using new CSS selectors with sufficient length for validation.</p>
                </div>
                <div class="article--authors">New CSS Author</div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/new-css"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: extraction succeeds using V2's new CSS selectors
        assert content.title == "New CSS Title"
        assert content.author == "New CSS Author"
        assert content.full_text.startswith("Content using new CSS")
