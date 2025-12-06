"""Article extractor for Jamaica Gleaner news source."""
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from .models import ExtractedArticleContent


class GleanerExtractor:
    """
    Extraction strategy for Jamaica Gleaner articles.

    Implements ArticleExtractor Protocol for jamaica-gleaner.com.

    HTML Structure (validated 2025-11-28):
    - Article title: <h1 class="title">
    - Article content: <div class="article-content"> with <p> tags
    - Author: <a class="author-term">
    - Published date: <meta property="article:published_time"> (ISO 8601 format)
    """

    def extract(self, html: str, url: str) -> ExtractedArticleContent:
        """
        Extract article content from Gleaner HTML.

        Args:
            html: Raw HTML content
            url: Article URL (for error context)

        Returns:
            ArticleContent with extracted data

        Raises:
            ValueError: If required elements (title, full_text) are missing
        """
        soup = BeautifulSoup(html, "lxml")

        # Extract title (required)
        title = self._extract_title(soup, url)

        # Extract full text (required)
        full_text = self._extract_full_text(soup, url)

        # Extract author (optional)
        author = self._extract_author(soup)

        # Extract published date (optional)
        published_date = self._extract_published_date(soup)

        return ExtractedArticleContent(
            title=title,
            full_text=full_text,
            author=author,
            published_date=published_date,
        )

    def _extract_title(self, soup: BeautifulSoup, url: str) -> str:
        """Extract article title."""
        # Primary selector: h1 with class="title"
        title_tag = soup.find("h1", class_="title")

        if title_tag:
            title_text = title_tag.get_text(strip=True)
            if title_text:
                return title_text

        # Fallback: try any h1
        h1_tag = soup.find("h1")
        if h1_tag:
            title_text = h1_tag.get_text(strip=True)
            if title_text:
                return title_text

        # If no title found, raise error (fail-fast)
        raise ValueError(f"Could not extract title from article: {url}")

    def _extract_full_text(self, soup: BeautifulSoup, url: str) -> str:
        """Extract article body paragraphs."""
        # Primary selector: div with class="article-content"
        content_container = soup.find("div", class_="article-content")

        # Fallback: try field-name-body
        if not content_container:
            content_container = soup.find("div", class_="field-name-body")

        if not content_container:
            raise ValueError(f"Could not find article content container: {url}")

        # Extract all paragraphs
        paragraphs = content_container.find_all("p")

        if not paragraphs:
            raise ValueError(f"No paragraphs found in article content: {url}")

        # Join paragraphs with double newline
        # Filter out empty paragraphs and email addresses (last paragraph often contains reporter email)
        valid_paragraphs = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            # Skip empty paragraphs and email-only paragraphs
            if text and not text.endswith("@gleanerjm.com"):
                valid_paragraphs.append(text)

        full_text = "\n\n".join(valid_paragraphs)

        if not full_text or len(full_text) < 50:
            raise ValueError(f"Extracted text too short or empty: {url}")

        return full_text

    def _extract_author(self, soup: BeautifulSoup) -> str | None:
        """Extract author name (optional)."""
        # Primary selector: a tag with class="author-term"
        author_link = soup.find("a", class_="author-term")

        if author_link:
            author_text = author_link.get_text(strip=True)
            if author_text:
                # Clean up common patterns like "By " prefix or "/Staff Reporter" suffix
                author_text = author_text.replace("By ", "").replace("by ", "")
                # Remove "/Staff Reporter" suffix if present
                if "/Staff Reporter" in author_text:
                    author_text = author_text.split("/")[0].strip()
                return author_text

        return None

    def _extract_published_date(self, soup: BeautifulSoup) -> datetime | None:
        """Extract published date (optional)."""
        # Primary selector: meta tag with property="article:published_time"
        meta_date = soup.find("meta", property="article:published_time")

        if meta_date:
            content = meta_date.get("content")
            if content:
                try:
                    # Parse ISO 8601 format datetime
                    dt = datetime.fromisoformat(content)
                    # Ensure timezone-aware (convert to UTC)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        # Convert to UTC for consistency
                        dt = dt.astimezone(timezone.utc)
                    return dt
                except (ValueError, TypeError) as e:
                    # If parsing fails, return None (date is optional)
                    pass

        # Fallback: try time tag with datetime attribute
        time_tag = soup.find("time")
        if time_tag:
            datetime_attr = time_tag.get("datetime")
            if datetime_attr:
                try:
                    dt = datetime.fromisoformat(datetime_attr)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = dt.astimezone(timezone.utc)
                    return dt
                except (ValueError, TypeError):
                    pass

        return None
