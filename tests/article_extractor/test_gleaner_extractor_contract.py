"""External service contract test for GleanerExtractor.

This test validates that the Jamaica Gleaner website structure hasn't changed
in ways that would break our extractor. It makes a live HTTP request to verify
the current site structure matches our implementation expectations.

Run with: uv run pytest tests/article_extractor/test_gleaner_extractor_contract.py -m contract -v
"""
import pytest
import requests

from src.article_extractor.gleaner_extractor import GleanerExtractor


class TestGleanerExtractorExternalContract:
    """External contract test that validates live site structure."""

    @pytest.mark.external
    @pytest.mark.contract
    async def test_gleaner_site_structure_unchanged(self):
        """
        Verify Gleaner site structure hasn't changed.

        This test detects breaking changes to the Jamaica Gleaner website
        by validating that our extractor can successfully parse a known
        live article. If this test fails, the site layout changed and
        GleanerExtractor needs updates.

        The test validates:
        - JSON-LD structured data exists and is parseable
        - Article body content is extractable via CSS selectors
        - Title, author, date, and full text extraction all work correctly
        """
        # Given: Known live Gleaner article URL (reference article from Dec 2025)
        url = "https://jamaica-gleaner.com/article/news/20251210/embrace-one-health"

        # When: Fetching and extracting content from live site
        response = requests.get(
            url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (compatible; JaacountableBot/1.0)"},
        )
        response.raise_for_status()
        html = response.text

        extractor = GleanerExtractor()
        content = extractor.extract(html, url)

        # Then: Extraction succeeds (validates entire structure: JSON-LD + CSS)
        # This comprehensive assertion ensures both parsing strategies work

        # Title should be extracted (from JSON-LD or CSS fallback)
        assert content.title is not None
        assert len(content.title) > 0

        # Full text should be extracted (from CSS selectors)
        assert content.full_text is not None
        assert len(content.full_text) >= 50

        # This specific article has author (validates JSON-LD author parsing)
        assert content.author is not None
        assert len(content.author) > 0

        # This specific article has date (validates JSON-LD date parsing)
        assert content.published_date is not None
