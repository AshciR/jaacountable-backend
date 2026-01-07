"""
POC script for newspaper archive extraction and classification.

Tests whether we can:
1. Extract article OCR text from https://gleaner.newspaperarchive.com historical pages
2. Use the existing CorruptionClassifier to classify historical content

Usage:
    uv run python scripts/poc_newspaper_archive.py <archive_url>

Example:
    uv run python scripts/poc_newspaper_archive.py "https://gleaner.newspaperarchive.com/kingston-gleaner/2020-01-01/"

Requirements:
    - OPENAI_API_KEY in .env file (required by CorruptionClassifier)
"""
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.article_classification.models import ClassificationInput, ClassificationResult
from src.article_classification.classifiers.corruption_classifier import CorruptionClassifier


# HTTP headers to mimic browser request (similar to successful curl command)
# Note: requests library handles gzip decompression automatically
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def fetch_archive_page(url: str) -> str:
    """
    Fetch newspaper archive page with proper HTTP headers.

    Args:
        url: Archive page URL

    Returns:
        Raw HTML content

    Raises:
        Exception: If fetch fails
    """
    logger.info(f"Fetching archive page: {url}")

    try:
        # Fetch with automatic decompression
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()

        # Ensure proper encoding (requests should auto-detect, but be explicit)
        response.encoding = response.apparent_encoding or 'utf-8'

        html_content = response.text

        # Validate response
        if len(html_content) < 1000:
            raise ValueError(f"Response too short ({len(html_content)} bytes) - might be error page")

        # Check if it looks like HTML
        if not html_content.strip().startswith('<!DOCTYPE') and not html_content.strip().startswith('<html'):
            raise ValueError("Response doesn't appear to be HTML")

        logger.info(f"✓ Page fetched successfully ({len(html_content)} characters)")
        return html_content

    except requests.RequestException as e:
        logger.error(f"Failed to fetch page: {e}")
        raise


def extract_ocr_content(html: str, url: str) -> dict:
    """
    Extract OCR text and metadata from archive page HTML.

    Uses BeautifulSoup with fallback strategies similar to GleanerExtractor.

    Args:
        html: Raw HTML content
        url: Page URL for error context

    Returns:
        dict with keys: title, full_text, published_date

    Raises:
        ValueError: If required fields cannot be extracted
    """
    logger.info("Parsing HTML to extract OCR content...")

    soup = BeautifulSoup(html, "lxml")

    # Extract title (try multiple strategies)
    title = _extract_title(soup, url)

    # Extract full text (OCR content)
    full_text = _extract_full_text(soup, url)

    # Extract published date (try to parse from URL or page)
    published_date = _extract_published_date(soup, url)

    logger.info(f"✓ Extraction successful - Title: '{title[:50]}...', Text: {len(full_text)} chars")

    return {
        "title": title,
        "full_text": full_text,
        "published_date": published_date,
    }


def _extract_title(soup: BeautifulSoup, url: str) -> str:
    """Extract article title with fallback chain."""
    # Priority 1: h1 tag
    h1_tag = soup.find("h1")
    if h1_tag:
        title_text = h1_tag.get_text(strip=True)
        if title_text:
            return title_text

    # Priority 2: meta og:title
    meta_title = soup.find("meta", property="og:title")
    if meta_title:
        content = meta_title.get("content")
        if content and content.strip():
            return content.strip()

    # Priority 3: title tag
    title_tag = soup.find("title")
    if title_tag:
        title_text = title_tag.get_text(strip=True)
        if title_text:
            return title_text

    # Fallback: Generate title from URL date
    try:
        # Extract date from URL like /2020-01-01/
        if "/20" in url:
            date_part = [part for part in url.split("/") if part.startswith("20")]
            if date_part:
                return f"Gleaner Archive - {date_part[0]}"
    except:
        pass

    raise ValueError(f"Could not extract title from archive page: {url}")


def _extract_full_text(soup: BeautifulSoup, url: str) -> str:
    """
    Extract OCR text content with fallback chain.

    Looks for newspaper archive OCR content patterns.
    """
    # Strategy 1: Look for organicOCRSection > textArea (newspaper archive specific)
    ocr_section = soup.find("div", class_="organicOCRSection")
    if ocr_section:
        text_area = ocr_section.find("div", class_="textArea")
        if text_area:
            text = text_area.get_text(strip=True)
            if text and len(text) >= 50:
                return text

    # Strategy 2: Look for any div with class containing "textArea"
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
                return full_text

    # Strategy 3: Look for divs with "ocr" in class name
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
                return full_text

    # Strategy 4: Look for paragraphs with substantial text
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
                return full_text

    # Strategy 5: Get all text from main/article tags
    for tag_name in ["main", "article"]:
        content_tag = soup.find(tag_name)
        if content_tag:
            text = content_tag.get_text(strip=True)
            if text and len(text) >= 50:
                return text

    raise ValueError(f"Could not extract sufficient text content (min 50 chars) from: {url}")


def _extract_published_date(soup: BeautifulSoup, url: str) -> datetime | None:
    """
    Extract published date with fallback chain.

    Returns timezone-aware datetime in UTC or None if not found.
    """
    # Strategy 1: Parse from URL (e.g., /2020-01-01/)
    try:
        parts = url.split("/")
        for part in parts:
            if len(part) == 10 and part.count("-") == 2:  # YYYY-MM-DD format
                dt = datetime.fromisoformat(part)
                return dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        pass

    # Strategy 2: Look for meta tags
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
                return dt
            except (ValueError, TypeError):
                pass

    # Strategy 3: Look for time tag
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

    # Return None if date not found (ClassificationInput allows this)
    return None


def build_classification_input(extracted_data: dict, url: str) -> ClassificationInput:
    """
    Build ClassificationInput from extracted archive data.

    Args:
        extracted_data: Dict from extract_ocr_content()
        url: Archive page URL

    Returns:
        Valid ClassificationInput object

    Raises:
        ValueError: If validation fails
    """
    logger.info("Building ClassificationInput...")

    try:
        input_data = ClassificationInput(
            url=url,
            title=extracted_data["title"],
            section="archive",
            full_text=extracted_data["full_text"],
            published_date=extracted_data["published_date"],
        )

        logger.info("✓ ClassificationInput created and validated")
        return input_data

    except Exception as e:
        logger.error(f"Failed to create ClassificationInput: {e}")
        raise


async def test_corruption_classifier(classification_input: ClassificationInput) -> ClassificationResult:
    """
    Test the corruption classifier with historical archive content.

    Args:
        classification_input: Validated input data

    Returns:
        ClassificationResult with relevance decision

    Raises:
        Exception: If classification fails
    """
    logger.info("Running corruption classifier...")

    try:
        classifier = CorruptionClassifier()
        result = await classifier.classify(classification_input)

        logger.info("✓ Classification complete")
        return result

    except Exception as e:
        logger.error(f"Classification failed: {e}")
        raise


def display_results(extracted_data: dict, result: ClassificationResult) -> None:
    """Display structured POC results."""
    print("\n" + "=" * 70)
    print("EXTRACTION RESULTS")
    print("=" * 70)
    print(f"Title: {extracted_data['title']}")
    print(f"Published: {extracted_data['published_date'] or 'Unknown'}")
    print(f"Text Length: {len(extracted_data['full_text'])} characters")
    print(f"\nFirst 200 chars of text:\n{extracted_data['full_text'][:200]}...")

    print("\n" + "=" * 70)
    print("CLASSIFICATION RESULTS")
    print("=" * 70)
    print(f"Relevant: {result.is_relevant}")
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Classifier: {result.classifier_type.value}")
    print(f"Model: {result.model_name}")

    print(f"\nReasoning:\n{result.reasoning}")

    if result.key_entities:
        print(f"\nKey Entities:")
        for entity in result.key_entities:
            print(f"  - {entity}")

    print("\n" + "=" * 70)
    print("POC COMPLETE")
    print("=" * 70)
    if result.is_relevant:
        print("✓ Successfully extracted and classified historical archive content")
        print("✓ Classifier identified this as relevant to corruption/accountability")
    else:
        print("✓ Successfully extracted and classified historical archive content")
        print("✗ Classifier determined this article is NOT relevant")


def discover_html_structure(html: str) -> None:
    """
    Analyze HTML structure to find OCR content locations.

    Prints diagnostic information about potential content containers.
    """
    soup = BeautifulSoup(html, "lxml")

    print("\n" + "=" * 70)
    print("HTML STRUCTURE DISCOVERY")
    print("=" * 70)

    # Find ALL divs and their classes
    print("\n1. ALL DIV elements found:")
    divs = soup.find_all("div")
    print(f"   Total <div> tags: {len(divs)}")

    # Show all unique classes
    all_classes = set()
    for div in divs:
        classes = div.get("class", [])
        if classes:
            for cls in classes:
                all_classes.add(cls)

    print(f"\n   Unique classes found:")
    for cls in sorted(all_classes):
        print(f"     - {cls}")

    # Find divs with substantial text
    print("\n2. DIVs with >50 characters of text:")
    text_divs = []
    for div in divs:
        text = div.get_text(strip=True)
        if len(text) > 50:
            classes = div.get("class", [])
            id_attr = div.get("id", "")
            text_divs.append({
                "classes": " ".join(classes) if classes else "(no class)",
                "id": id_attr or "(no id)",
                "text_length": len(text),
                "sample": text[:150]
            })

    # Sort by text length
    text_divs.sort(key=lambda x: x["text_length"], reverse=True)
    for i, div_info in enumerate(text_divs[:10], 1):  # Top 10
        print(f"\n  {i}. Class: {div_info['classes']}")
        print(f"     ID: {div_info['id']}")
        print(f"     Length: {div_info['text_length']} chars")
        print(f"     Sample: {div_info['sample']}...")

    # Find all paragraphs
    print("\n2. Paragraphs found:")
    paragraphs = soup.find_all("p")
    print(f"   Total <p> tags: {len(paragraphs)}")
    if paragraphs:
        total_p_text = sum(len(p.get_text(strip=True)) for p in paragraphs)
        print(f"   Total text in paragraphs: {total_p_text} chars")

    # Find script tags (might contain JSON data)
    print("\n3. Script tags:")
    scripts = soup.find_all("script")
    print(f"   Total <script> tags: {len(scripts)}")
    for script in scripts[:5]:  # First 5
        script_type = script.get("type", "text/javascript")
        content_preview = script.string[:100] if script.string else "(no content)"
        print(f"   - Type: {script_type}, Content: {content_preview}...")

    # Save HTML for manual inspection
    html_file = "/tmp/archive_page.html"
    Path(html_file).write_text(html)
    print(f"\n✓ Full HTML saved to: {html_file}")
    print("  Open this file to manually inspect the structure")


async def main() -> None:
    """Main POC workflow."""
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/poc_newspaper_archive.py <archive_url> [--discover]")
        print("\nExample:")
        print('  uv run python scripts/poc_newspaper_archive.py "https://gleaner.newspaperarchive.com/kingston-gleaner/2020-01-01/" --discover')
        print('  uv run python scripts/poc_newspaper_archive.py "https://gleaner.newspaperarchive.com/kingston-gleaner/2020-01-01/"')
        sys.exit(1)

    url = sys.argv[1]
    discover_mode = "--discover" in sys.argv

    logger.info("=" * 70)
    logger.info("POC: Newspaper Archive Extraction & Classification")
    logger.info("=" * 70)
    logger.info(f"URL: {url}")
    logger.info(f"Mode: {'DISCOVERY' if discover_mode else 'EXTRACTION & CLASSIFICATION'}")
    logger.info("")

    try:
        # Step 1: Fetch archive page
        html = fetch_archive_page(url)

        # If discovery mode, analyze structure and exit
        if discover_mode:
            discover_html_structure(html)
            print("\n✓ Discovery complete. Review the output and /tmp/archive_page.html")
            print("  Then run without --discover flag to extract and classify")
            return

        # Step 2: Extract OCR content
        extracted_data = extract_ocr_content(html, url)

        # Step 3: Build ClassificationInput
        classification_input = build_classification_input(extracted_data, url)

        # Step 4: Test corruption classifier
        result = await test_corruption_classifier(classification_input)

        # Step 5: Display results
        display_results(extracted_data, result)

    except Exception as e:
        logger.error(f"\n❌ POC FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
