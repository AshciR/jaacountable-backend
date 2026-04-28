"""Shared fixtures for article extractor tests."""
import pytest
from pathlib import Path


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to HTML fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def gleaner_html_v2(fixtures_dir: Path) -> str:
    """Load Gleaner article HTML fixture with JSON-LD structure (V2)."""
    return (fixtures_dir / "gleaner_article_v2.html").read_text(encoding="utf-8")


@pytest.fixture
def gleaner_html_v1(fixtures_dir: Path) -> str:
    """Load Gleaner article HTML fixture with legacy CSS structure (V1)."""
    return (fixtures_dir / "gleaner_article_v1.html").read_text(encoding="utf-8")


@pytest.fixture
def gleaner_html_v2_premium(fixtures_dir: Path) -> str:
    """Load Gleaner premium article HTML fixture (paywalled, no article--body)."""
    return (fixtures_dir / "gleaner_article_v2_premium.html").read_text(encoding="utf-8")


@pytest.fixture
def gleaner_archive_html(fixtures_dir: Path) -> str:
    """Load Gleaner archive page HTML fixture (OCR-based historical newspaper)."""
    return (fixtures_dir / "gleaner_archive_2021-11-07-page-5.html").read_text(encoding="utf-8")


@pytest.fixture
def gleaner_archive_page_with_multiple_articles(fixtures_dir: Path) -> str:
    """Load Gleaner archive page with multiple articles (HEART article + congratulations message)."""
    return (fixtures_dir / "gleaner_archive_2021-11-07-page-3.html").read_text(encoding="utf-8")


@pytest.fixture
def jamaica_observer_html(fixtures_dir: Path) -> str:
    """Load Jamaica Observer article HTML (pipe-delimited author with email)."""
    return (fixtures_dir / "jamaica_observer_article.html").read_text(encoding="utf-8")


@pytest.fixture
def jamaica_observer_html_by_prefix(fixtures_dir: Path) -> str:
    """Load Jamaica Observer article HTML (space-delimited author with BY prefix)."""
    return (fixtures_dir / "jamaica_observer_article_by_prefix.html").read_text(encoding="utf-8")


@pytest.fixture
def jamaica_observer_html_pipe_no_email(fixtures_dir: Path) -> str:
    """Load Jamaica Observer article HTML (pipe-delimited author without email)."""
    return (fixtures_dir / "jamaica_observer_article_pipe_no_email.html").read_text(encoding="utf-8")
