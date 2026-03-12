"""Article extractor for Jamaica Observer news source (JSON-LD + CSS hybrid)."""
import json
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from src.article_extractor.models import ExtractedArticleContent


class JamaicaObserverExtractor:
    """
    Extraction strategy for Jamaica Observer articles (JSON-LD + CSS hybrid).

    Implements ArticleExtractor Protocol for jamaicaobserver.com.

    Uses hybrid parsing approach:
    1. JSON-LD structured data for metadata (title, author, date) - more stable
    2. CSS selectors for article body text (JSON-LD doesn't include full text)
    3. Fallback CSS selectors for backward compatibility

    HTML Structure (validated 2026-03-12):
    - JSON-LD: <script type="application/ld+json"> with Schema.org NewsArticle
    - Article title: headline field in JSON-LD (fallback: h1.title)
    - Article content: <div class="body"> with <p> tags (fallback: article.article)
    - Author: author[0].name field in JSON-LD (fallback: span.author)
    - Published date: datePublished field in JSON-LD (fallback: meta[article:published_time])

    Author name formats (inconsistent across the site, all handled):
    1. Pipe-delimited with email: "Daniel Blake | Sports Writer | blaked@jamaicaobserver.com"
    2. Pipe-delimited without email: "Jerome Williams | Reporter"
    3. Space-delimited with "BY" prefix: "BY ALICIA DUNKLEY WILLIS Senior reporter email@..."
    Cleaning strategy: strip "BY " prefix → remove email token → split on "|" → take first part.
    Note: format 3 may retain the job title in the result (known site inconsistency).
    """

    def extract(self, html: str, url: str) -> ExtractedArticleContent:
        """
        Extract article content from Jamaica Observer HTML using JSON-LD + CSS parsing.

        Args:
            html: Raw HTML content
            url: Article URL (for error context)

        Returns:
            ExtractedArticleContent with extracted data

        Raises:
            ValueError: If required elements (title, full_text) are missing
        """
        soup = BeautifulSoup(html, "lxml")

        json_ld = self._extract_json_ld(soup)

        title = self._extract_title(soup, json_ld, url)
        full_text = self._extract_full_text(soup, url)

        author = self._extract_author(soup, json_ld)
        published_date = self._extract_published_date(soup, json_ld)

        return ExtractedArticleContent(
            title=title,
            full_text=full_text,
            author=author,
            published_date=published_date,
        )

    def _extract_json_ld(self, soup: BeautifulSoup) -> dict | None:
        """
        Extract and parse JSON-LD structured data from HTML.

        Args:
            soup: BeautifulSoup parsed HTML

        Returns:
            Parsed JSON-LD dict if found and valid, None otherwise
        """
        json_ld_scripts = soup.find_all("script", type="application/ld+json")

        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                # Jamaica Observer uses NewsArticle (vs Gleaner's Article)
                if isinstance(data, dict) and data.get("@type") == "NewsArticle":
                    return data
            except (json.JSONDecodeError, TypeError, AttributeError):
                continue

        return None

    def _extract_title(self, soup: BeautifulSoup, json_ld: dict | None, url: str) -> str:
        """
        Extract article title with priority fallback chain.

        Priority:
        1. JSON-LD headline field (most reliable)
        2. h1.title (site structure)
        3. Any h1 tag (last resort)

        Args:
            soup: BeautifulSoup parsed HTML
            json_ld: Parsed JSON-LD data (or None)
            url: Article URL for error context

        Returns:
            Article title string

        Raises:
            ValueError: If title cannot be extracted from any source
        """
        # Priority 1: JSON-LD headline
        if json_ld and "headline" in json_ld:
            headline = json_ld["headline"]
            if isinstance(headline, str) and headline.strip():
                return headline.strip()

        # Priority 2: h1 with class="title"
        title_tag = soup.find("h1", class_="title")
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            if title_text:
                return title_text

        # Priority 3: Any h1 tag (last resort)
        h1_tag = soup.find("h1")
        if h1_tag:
            title_text = h1_tag.get_text(strip=True)
            if title_text:
                return title_text

        raise ValueError(f"Could not extract title from article: {url}")

    def _extract_full_text(self, soup: BeautifulSoup, url: str) -> str:
        """
        Extract article body paragraphs with priority fallback chain.

        Priority:
        1. div.body (primary site structure)
        2. article.article (fallback)

        Args:
            soup: BeautifulSoup parsed HTML
            url: Article URL for error context

        Returns:
            Full article text as string

        Raises:
            ValueError: If article body cannot be extracted or is too short
        """
        content_container = None

        # Priority 1: div.body
        content_container = soup.find("div", class_="body")

        # Priority 2: article.article
        if not content_container:
            content_container = soup.find("article", class_="article")

        if not content_container:
            raise ValueError(f"Could not find article content container: {url}")

        paragraphs = content_container.find_all("p")

        if not paragraphs:
            raise ValueError(f"No paragraphs found in article content: {url}")

        # Filter out empty paragraphs and email-only paragraphs
        valid_paragraphs = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            if text and "@jamaicaobserver.com" not in text:
                valid_paragraphs.append(text)

        full_text = "\n\n".join(valid_paragraphs)

        if not full_text or len(full_text) < 50:
            raise ValueError(f"Extracted text too short or empty: {url}")

        return full_text

    def _extract_author(self, soup: BeautifulSoup, json_ld: dict | None) -> str | None:
        """
        Extract author name with priority fallback chain (optional field).

        Priority:
        1. JSON-LD author[0].name field (most reliable)
        2. span.author (CSS fallback)

        Args:
            soup: BeautifulSoup parsed HTML
            json_ld: Parsed JSON-LD data (or None)

        Returns:
            Author name string or None if not found
        """
        # Priority 1: JSON-LD author (array — take first element)
        if json_ld and "author" in json_ld:
            author_field = json_ld["author"]
            if isinstance(author_field, list) and author_field:
                author_obj = author_field[0]
            elif isinstance(author_field, dict):
                author_obj = author_field
            else:
                author_obj = None

            if isinstance(author_obj, dict) and author_obj.get("@type") == "Person":
                author_name = author_obj.get("name")
                if isinstance(author_name, str) and author_name.strip():
                    return self._clean_author_name(author_name.strip())

        # Priority 2: span.author (CSS fallback)
        author_span = soup.find("span", class_="author")
        if author_span:
            author_text = author_span.get_text(strip=True)
            if author_text:
                return self._clean_author_name(author_text)

        return None

    def _extract_published_date(self, soup: BeautifulSoup, json_ld: dict | None) -> datetime | None:
        """
        Extract published date with priority fallback chain (optional field).

        Priority:
        1. JSON-LD datePublished field (most reliable)
        2. meta[property="article:published_time"] (fallback)

        Args:
            soup: BeautifulSoup parsed HTML
            json_ld: Parsed JSON-LD data (or None)

        Returns:
            Timezone-aware datetime in UTC or None if not found
        """
        # Priority 1: JSON-LD datePublished
        if json_ld and "datePublished" in json_ld:
            date_str = json_ld["datePublished"]
            if isinstance(date_str, str):
                parsed_date = self._parse_and_normalize_date(date_str)
                if parsed_date:
                    return parsed_date

        # Priority 2: meta tag with property="article:published_time"
        meta_date = soup.find("meta", property="article:published_time")
        if meta_date:
            content = meta_date.get("content")
            if content:
                parsed_date = self._parse_and_normalize_date(content)
                if parsed_date:
                    return parsed_date

        return None

    def _clean_author_name(self, author_text: str) -> str:
        """
        Clean up author name handling three observed formats on the site.

        Formats observed (2026-03-12):
        1. Pipe-delimited with email:    "Daniel Blake | Sports Writer | blaked@jamaicaobserver.com"
        2. Pipe-delimited without email: "Jerome Williams | Reporter"
        3. Space-delimited with BY:      "BY ALICIA DUNKLEY WILLIS Senior reporter email@..."

        Cleaning strategy (applied in order):
        1. Strip "BY " / "by " prefix
        2. Remove email token (regex: \\s*\\S+@\\S+)
        3. If "|" present: split, take first segment
        4. Strip whitespace

        Note: Format 3 may retain the job title in the result (e.g. "ALICIA DUNKLEY WILLIS
        Senior reporter") as there is no delimiter separating name from title.

        Args:
            author_text: Raw author name string

        Returns:
            Cleaned author name string
        """
        # Step 1: Remove "BY " / "by " prefix
        if author_text.upper().startswith("BY "):
            author_text = author_text[3:]

        # Step 2: Remove email address token
        author_text = re.sub(r"\s*\S+@\S+", "", author_text)

        # Step 3: Split on "|" and take first part
        if "|" in author_text:
            author_text = author_text.split("|")[0]

        return author_text.strip()

    def _parse_and_normalize_date(self, date_str: str) -> datetime | None:
        """
        Parse ISO 8601 date string and normalize to timezone-aware UTC datetime.

        Args:
            date_str: ISO 8601 formatted date string

        Returns:
            Timezone-aware datetime in UTC or None if parsing fails
        """
        try:
            dt = datetime.fromisoformat(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None
