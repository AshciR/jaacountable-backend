"""Shared fixtures for article discovery tests."""

import pytest
from pathlib import Path


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to HTML fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def archive_page_nov_07_page_1(fixtures_dir: Path) -> str:
    """Load Nov 07 archive page 1 with next link to page 2."""
    return (fixtures_dir / "archive_page_nov_07_page_1.html").read_text(encoding="utf-8")


@pytest.fixture
def archive_page_nov_07_page_2(fixtures_dir: Path) -> str:
    """Load Nov 07 archive page 2 with prev link to page 1 and next link to page 3."""
    return (fixtures_dir / "archive_page_nov_07_page_2.html").read_text(encoding="utf-8")


@pytest.fixture
def archive_page_nov_07_page_3(fixtures_dir: Path) -> str:
    """Load Nov 07 archive page 3 with prev link to page 2 and next link to page 4."""
    return (fixtures_dir / "archive_page_nov_07_page_3.html").read_text(encoding="utf-8")


@pytest.fixture
def archive_page_nov_07_page_4(fixtures_dir: Path) -> str:
    """Load Nov 07 archive page 4 (last page) with prev link to page 3."""
    return (fixtures_dir / "archive_page_nov_07_page_4.html").read_text(encoding="utf-8")


@pytest.fixture
def archive_page_no_og_title(fixtures_dir: Path) -> str:
    """Load archive page without og:title (only title tag)."""
    return (fixtures_dir / "archive_page_no_og_title.html").read_text(encoding="utf-8")


@pytest.fixture
def archive_page_no_title(fixtures_dir: Path) -> str:
    """Load archive page with no title tags."""
    return (fixtures_dir / "archive_page_no_title.html").read_text(encoding="utf-8")


@pytest.fixture
def archive_page_malformed(fixtures_dir: Path) -> str:
    """Load malformed archive page HTML."""
    return (fixtures_dir / "archive_page_malformed.html").read_text(encoding="utf-8")


@pytest.fixture
def archive_page_nov_06(fixtures_dir: Path) -> str:
    """Load archive page for November 6, 2021 (single page)."""
    return (fixtures_dir / "archive_page_nov_06.html").read_text(encoding="utf-8")


@pytest.fixture
def archive_page_nov_05(fixtures_dir: Path) -> str:
    """Load archive page for November 5, 2021 (single page)."""
    return (fixtures_dir / "archive_page_nov_05.html").read_text(encoding="utf-8")
