"""Article extractor for Jamaica Gleaner with automatic fallback strategy."""
import logging

from .models import ExtractedArticleContent
from .gleaner_extractor_v1 import GleanerExtractorV1
from .gleaner_extractor_v2 import GleanerExtractorV2


logger = logging.getLogger(__name__)


class GleanerExtractor:
    """
    Jamaica Gleaner extractor with automatic V2→V1 fallback.

    Implements ArticleExtractor Protocol with resilient extraction strategy:
    1. Try V2 extractor (JSON-LD + CSS hybrid) - more comprehensive
    2. If V2 fails with ValueError, fallback to V1 (CSS-only) - simpler/more robust
    3. Log which version succeeded for observability

    This dual-version approach provides:
    - Better success rate (V2 tries first for richer extraction)
    - Resilience to site structure changes (V1 fallback when V2 fails)
    - Observability (logs track which version succeeded)
    - Zero changes required to service layer (implements same Protocol)

    Example Success Flow (V2 succeeds):
        extractor = GleanerExtractor()
        content = extractor.extract(html, url)
        # Log: "Successfully extracted using V2 extractor (JSON-LD + CSS)"

    Example Fallback Flow (V2 fails, V1 succeeds):
        extractor = GleanerExtractor()
        content = extractor.extract(html, url)
        # Log: "V2 extractor (JSON-LD + CSS) failed: Could not extract title..."
        # Log: "Falling back to V1 extractor"
        # Log: "Successfully extracted using V1 extractor (CSS-only)"
    """

    def __init__(self):
        """Initialize both V1 and V2 extractors."""
        self.v2_extractor = GleanerExtractorV2()
        self.v1_extractor = GleanerExtractorV1()

    def extract(self, html: str, url: str) -> ExtractedArticleContent:
        """
        Extract article content with automatic V2→V1 fallback using list iteration pattern.

        Args:
            html: Raw HTML content
            url: Article URL (for error context)

        Returns:
            ExtractedArticleContent from V2 or V1 extractor

        Raises:
            ValueError: If all extractors fail
        """
        extractors = [
            (self.v2_extractor, "v2", "V2 extractor (JSON-LD + CSS)"),
            (self.v1_extractor, "v1", "V1 extractor (CSS-only)"),
        ]

        errors = []

        for extractor, version, description in extractors:
            try:
                content = extractor.extract(html, url)
                logger.info(
                    f"Successfully extracted using {description}",
                    extra={"url": url, "extractor_version": version}
                )
                return content
            except ValueError as error:
                errors.append((version, error))
                logger.warning(
                    f"{description} failed: {error}",
                    extra={"url": url, "extractor_version": version, "error": str(error)}
                )
                if version == "v2":
                    logger.info("Falling back to V1 extractor", extra={"url": url})

        # All extractors failed
        logger.error(
            "All extractors failed",
            extra={"url": url, "errors": [(v, str(e)) for v, e in errors]}
        )
        error_details = "; ".join([f"{v}: {e}" for v, e in errors])
        raise ValueError(f"All extractors failed. {error_details}")
