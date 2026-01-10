-- name: insert_article<!
-- Insert a new article and return the article record (excluding full_text)
INSERT INTO articles (
    url,
    title,
    section,
    published_date,
    fetched_at,
    full_text,
    news_source_id
)
VALUES (
    :url,
    :title,
    :section,
    :published_date,
    :fetched_at,
    :full_text,
    :news_source_id
)
RETURNING id, url, title, section, published_date, fetched_at, news_source_id;

-- name: get_existing_urls
-- Check which URLs from a list already exist in the database
-- Returns set of existing URLs for filtering
SELECT url
FROM articles
WHERE url = ANY(:urls::text[]);
