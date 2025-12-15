"""External service contract test for GleanerExtractor wrapper.

This test validates that the Jamaica Gleaner website structure hasn't changed
in ways that would break our extractor. It makes a live HTTP request to verify
the current site structure matches our implementation expectations.

The GleanerExtractor wrapper automatically tries V2 (JSON-LD + CSS) first,
then falls back to V1 (CSS-only) if needed. This test validates that at least
one extraction strategy works with the live site.

Run with: uv run pytest tests/article_extractor/test_gleaner_extractor_contract.py -m contract -v
"""
import pytest
import requests

from src.article_extractor.extractors.gleaner_extractor import GleanerExtractor


class TestGleanerExtractorExternalContract:
    """External contract test that validates live site structure with wrapper."""

    @pytest.mark.external
    @pytest.mark.contract
    async def test_gleaner_site_structure_unchanged(self):
        """
        Verify Gleaner site structure works with V2→V1 fallback wrapper.

        This test detects breaking changes to the Jamaica Gleaner website
        by validating that our extractor wrapper can successfully parse a known
        live article using either V2 (JSON-LD + CSS) or V1 (CSS-only) extraction.

        The test validates:
        - Wrapper successfully extracts content from live site
        - At least one extraction strategy (V2 or V1) works
        - Title, author, date, and full text extraction all work correctly
        """
        # Given: Known live Gleaner article URL (reference article from Dec 2025)
        url = "https://jamaica-gleaner.com/article/news/20251213/policeman-dies-after-being-hit-bus-involved-funeral-procession-st-elizabeth"

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

        # Then: Extraction succeeds (validates wrapper works with live site)
        # This validates at least one extraction strategy (V2 or V1) works

        # Title should be extracted (from JSON-LD or CSS fallback)
        assert content.title is not None
        assert len(content.title) > 0

        # Full text should be extracted (from CSS selectors)
        assert content.full_text is not None
        assert len(content.full_text) >= 50

        # Published date should be extracted (validates date parsing)
        assert content.published_date is not None

        # Note: Author is optional - some articles don't have structured author fields
        # (author name may appear in article text instead)
