import requests
import time


def fetch_gleaner_page(section: str, crawl_delay: int = 10) -> str:
    """
    Generic function to scrape any Jamaica Gleaner section.

    Args:
        section: The section path (e.g., 'lead', 'news', 'sports', 'entertainment')
        crawl_delay: Delay in seconds to respect crawl policies (default: 10)

    Returns:
        HTML content of the requested page
    """

    time.sleep(crawl_delay)  # Respect the crawl delay

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    url = f"https://jamaica-gleaner.com/{section}"

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.text
    except Exception as e:
        return f"Error fetching {section} section: {str(e)}"


def get_gleaner_lead_stories() -> str:
    """
    Scrapes the Jamaica Gleaner lead stories section.

    Returns:
        HTML content of the lead stories page
    """
    return fetch_gleaner_page("lead")


def get_gleaner_news_section() -> str:
    """
    Scrapes the Jamaica Gleaner news section.

    Returns:
        HTML content of the news section page
    """
    return fetch_gleaner_page("news")
