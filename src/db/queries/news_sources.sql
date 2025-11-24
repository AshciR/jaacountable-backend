-- name: insert_news_source<!
-- Insert a new news source and return the news source record
INSERT INTO news_sources (
    name,
    base_url,
    crawl_delay,
    is_active,
    last_scraped_at,
    created_at
)
VALUES (
    :name,
    :base_url,
    :crawl_delay,
    :is_active,
    :last_scraped_at,
    :created_at
)
RETURNING id, name, base_url, crawl_delay, is_active, last_scraped_at, created_at;
