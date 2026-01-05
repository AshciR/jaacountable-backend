"""
Extractor for Jamaica Gleaner newspaper archive articles.

Extracts article content from gleaner.newspaperarchive.com historical pages.
These are OCR-based scanned newspaper pages with different HTML structure
than modern Gleaner articles.
"""

import json
import os
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from litellm import completion
from loguru import logger

from src.article_extractor.models import ExtractedArticleContent

load_dotenv()
EXTRACTOR_API_KEY = os.getenv("OPENAI_EXTRACTOR_API_KEY")

class GleanerArchiveExtractor:
    """
    Extractor for Jamaica Gleaner newspaper archive (gleaner.newspaperarchive.com).

    Implements ArticleExtractor protocol for OCR-based historical newspaper pages.
    """

    def extract(self, html: str, url: str) -> ExtractedArticleContent:
        """
        Extract structured article content from archive page HTML.

        Args:
            html: Raw HTML content of the archive page
            url: Archive page URL (for context/debugging)

        Returns:
            ExtractedArticleContent with extracted fields

        Raises:
            ValueError: If required elements are missing or parsing fails
        """
        logger.info(f"Extracting archive article from: {url}")

        soup = BeautifulSoup(html, "lxml")

        # Extract all fields using priority fallback chains
        # Extract full_text first (needed for LLM-based title and author extraction)
        full_text = self._extract_full_text(soup, url)
        title = self._extract_title(soup, url, full_text)
        published_date = self._extract_published_date(soup, url)
        # Extract author using LLM (needs full_text for OCR analysis)
        author = self._extract_author(full_text)

        logger.info(
            f"✓ Archive extraction successful - Title: '{title[:50]}...', "
            f"Text: {len(full_text)} chars, Author: {author or 'None'}, "
            f"Date: {published_date or 'None'}"
        )

        return ExtractedArticleContent(
            title=title,
            full_text=full_text,
            author=author,
            published_date=published_date,
        )

    def _extract_title(self, soup: BeautifulSoup, url: str, full_text: str) -> str:
        """
        Extract article headline with LLM-based fallback chain.

        Priority:
        1. LLM extraction from OCR text (extracts actual headline)
        2. meta og:title (includes date/page context)
        3. h1 tag (usually generic "Kingston Gleaner")
        4. title tag
        5. Generate from URL date

        Args:
            soup: Parsed HTML
            url: Page URL for fallback generation
            full_text: Extracted OCR text

        Returns:
            Extracted title/headline

        Raises:
            ValueError: If no title can be extracted
        """
        # Priority 1: Use LLM to extract actual headline from OCR text
        try:
            # Use first 500 chars of text (headlines are at the start)
            text_sample = full_text[:500]

            logger.debug("Using LLM to extract headline from OCR text")
            response = completion(
                api_key=EXTRACTOR_API_KEY,
                model="openai/gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a precise headline extraction assistant. "
                            "Extract the article headline from OCR text of a scanned newspaper page. "
                            "The headline is typically in larger text near the start of the article body, "
                            "after the newspaper name and date. "
                            "Return ONLY the headline text, or 'NONE' if no clear headline is found. "
                            "Do not include the newspaper name, date, author name, or byline."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Extract the article headline from this newspaper OCR text:\n\n{text_sample}"
                    }
                ],
                temperature=0.0,  # Deterministic extraction
                max_tokens=100,   # Headlines are typically short
            )

            # Parse response
            headline = response.choices[0].message.content.strip()

            # Check if LLM found a headline
            if headline and headline.upper() != "NONE" and len(headline) > 5:
                logger.debug(f"Headline extracted via LLM: {headline}")
                return headline

        except Exception as e:
            logger.warning(f"LLM headline extraction failed: {e}. Falling back to HTML elements.")

        # Priority 2: meta og:title (has date/page context)
        meta_title = soup.find("meta", property="og:title")
        if meta_title:
            content = meta_title.get("content")
            if content and content.strip():
                logger.debug(f"Title extracted from og:title: {content[:50]}...")
                return content.strip()

        # Priority 3: h1 tag
        h1_tag = soup.find("h1")
        if h1_tag:
            title_text = h1_tag.get_text(strip=True)
            if title_text:
                logger.debug(f"Title extracted from h1 tag: {title_text[:50]}...")
                return title_text

        # Priority 4: title tag
        title_tag = soup.find("title")
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            if title_text:
                logger.debug(f"Title extracted from title tag: {title_text[:50]}...")
                return title_text

        # Priority 5: Generate from URL date
        try:
            if "/20" in url:  # Date part starts with "20" (2000-2099)
                date_part = [part for part in url.split("/") if part.startswith("20")]
                if date_part and len(date_part[0]) == 10:  # YYYY-MM-DD format
                    generated_title = f"Gleaner Archive - {date_part[0]}"
                    logger.debug(f"Title generated from URL date: {generated_title}")
                    return generated_title
        except Exception as e:
            logger.debug(f"Failed to generate title from URL: {e}")

        raise ValueError(f"Could not extract title from archive page: {url}")

    def _extract_full_text(self, soup: BeautifulSoup, url: str) -> str:
        """
        Extract OCR text content with comprehensive fallback chain.

        Priority:
        1. div.organicOCRSection > div.textArea (archive-specific)
        2. All div.textArea elements
        3. Divs with "ocr" in class name
        4. Paragraph tags with minimum length
        5. main or article tags

        Args:
            soup: Parsed HTML
            url: Page URL for error messages

        Returns:
            Extracted full text (minimum 50 chars)

        Raises:
            ValueError: If text extraction fails or text < 50 chars
        """
        # Strategy 1: organicOCRSection > textArea (archive-specific)
        ocr_section = soup.find("div", class_="organicOCRSection")
        if ocr_section:
            text_area = ocr_section.find("div", class_="textArea")
            if text_area:
                text = text_area.get_text(strip=True)
                if text and len(text) >= 50:
                    logger.debug(f"Text extracted from organicOCRSection: {len(text)} chars")
                    return text

        # Strategy 2: All textArea divs
        text_areas = soup.find_all("div", class_="textArea")
        if text_areas:
            texts = []
            for div in text_areas:
                text = div.get_text(strip=True)
                if text and len(text) > 50:
                    texts.append(text)

            if texts:
                full_text = "\n\n".join(texts)
                if len(full_text) >= 50:
                    logger.debug(f"Text extracted from textArea divs: {len(full_text)} chars")
                    return full_text

        # Strategy 3: Divs with "ocr" in class name
        ocr_divs = soup.find_all("div", class_=lambda c: c and "ocr" in str(c).lower())
        if ocr_divs:
            texts = []
            for div in ocr_divs:
                text = div.get_text(strip=True)
                if text and len(text) > 50:
                    texts.append(text)

            if texts:
                full_text = "\n\n".join(texts)
                if len(full_text) >= 50:
                    logger.debug(f"Text extracted from OCR divs: {len(full_text)} chars")
                    return full_text

        # Strategy 4: Paragraph tags with minimum length
        paragraphs = soup.find_all("p")
        if paragraphs:
            valid_paragraphs = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text and len(text) > 20:  # Minimum paragraph length
                    valid_paragraphs.append(text)

            if valid_paragraphs:
                full_text = "\n\n".join(valid_paragraphs)
                if len(full_text) >= 50:
                    logger.debug(f"Text extracted from paragraphs: {len(full_text)} chars")
                    return full_text

        # Strategy 5: main or article tags
        for tag_name in ["main", "article"]:
            content_tag = soup.find(tag_name)
            if content_tag:
                text = content_tag.get_text(strip=True)
                if text and len(text) >= 50:
                    logger.debug(f"Text extracted from {tag_name} tag: {len(text)} chars")
                    return text

        raise ValueError(
            f"Could not extract sufficient text content (min 50 chars) from archive page: {url}"
        )

    def _extract_author(self, full_text: str) -> str | None:
        """
        Extract author using LLM to parse OCR text (fail-soft).

        Archive articles often have author bylines in the OCR text
        (e.g., "Livern Barrett\nSenior Staff Reporter") that we can
        extract using an LLM.

        Args:
            full_text: Extracted OCR text

        Returns:
            Author name or None if not found
        """
        # Use LLM to extract author from OCR text
        try:
            # Use first 1000 chars of text (bylines are typically at the start)
            text_sample = full_text[:1000]

            logger.debug("Using LLM to extract author from OCR text")
            response = completion(
                model="openai/gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a precise text extraction assistant. "
                            "Extract the author's name from newspaper article text. "
                            "Look for bylines like 'By [Name]' or '[Name]\\nStaff Reporter'. "
                            "Return ONLY the author's full name, or 'NONE' if no author is found. "
                            "Do not include titles, job descriptions, or explanations."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Extract the author's name from this newspaper text:\n\n{text_sample}"
                    }
                ],
                temperature=0.0,  # Deterministic extraction
                max_tokens=50,    # Author names are short
            )

            # Parse response
            author_name = response.choices[0].message.content.strip()

            # Check if LLM found an author
            if author_name and author_name.upper() != "NONE":
                logger.debug(f"Author extracted via LLM: {author_name}")
                return author_name
            else:
                logger.debug("LLM could not find author in OCR text")
                return None

        except Exception as e:
            logger.warning(f"LLM author extraction failed: {e}. Returning None.")
            return None

    def _extract_published_date(self, soup: BeautifulSoup, url: str) -> datetime | None:
        """
        Extract published date with fallback chain (fail-soft).

        Priority:
        1. Parse from URL pattern (/YYYY-MM-DD/)
        2. meta article:published_time
        3. time[datetime] tag

        Returns timezone-aware datetime in UTC or None if not found.

        Args:
            soup: Parsed HTML
            url: Page URL for date extraction

        Returns:
            Timezone-aware UTC datetime or None
        """
        # Strategy 1: Parse from URL (most reliable for archives)
        # Archive URLs follow pattern: /kingston-gleaner/YYYY-MM-DD/page-N/
        try:
            parts = url.split("/")
            for part in parts:
                if len(part) == 10 and part.count("-") == 2:  # YYYY-MM-DD format
                    dt = datetime.fromisoformat(part)
                    utc_dt = dt.replace(tzinfo=timezone.utc)
                    logger.debug(f"Date extracted from URL: {utc_dt}")
                    return utc_dt
        except (ValueError, AttributeError) as e:
            logger.debug(f"Failed to parse date from URL: {e}")

        # Strategy 2: meta article:published_time
        meta_date = soup.find("meta", property="article:published_time")
        if meta_date:
            content = meta_date.get("content")
            if content:
                try:
                    dt = datetime.fromisoformat(content)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = dt.astimezone(timezone.utc)
                    logger.debug(f"Date extracted from meta tag: {dt}")
                    return dt
                except (ValueError, TypeError) as e:
                    logger.debug(f"Failed to parse date from meta tag: {e}")

        # Strategy 3: time[datetime] tag
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
                    logger.debug(f"Date extracted from time tag: {dt}")
                    return dt
                except (ValueError, TypeError) as e:
                    logger.debug(f"Failed to parse date from time tag: {e}")

        # Return None (acceptable for ExtractedArticleContent)
        logger.debug("No published date found in archive article")
        return None
