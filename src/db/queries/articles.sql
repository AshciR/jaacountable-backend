-- name: insert_article<!
-- Insert a new article and return the article record (excluding full_text)
INSERT INTO articles (
    url,
    title,
    section,
    published_date,
    fetched_at,
    full_text
)
VALUES (
    :url,
    :title,
    :section,
    :published_date,
    :fetched_at,
    :full_text
)
RETURNING id, url, title, section, published_date, fetched_at;
