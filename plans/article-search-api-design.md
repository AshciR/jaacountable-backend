# Article Search API Design

## Overview
Design an OpenAPI specification for searching articles in the jaacountable-backend system.

## Design Decisions (Confirmed)
- **Full-text search**: PostgreSQL Full-Text Search (tsvector/tsquery)
- **Pagination**: Offset/Limit (page-based)
- **Response**: Configurable via `include_full_text` parameter
- **V1 Filters**: Text search (q), date range, entity name

---

## Search Endpoint

### `GET /api/v1/articles/search`

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `q` | string | No | - | Full-text search query (uses PostgreSQL FTS on title + full_text) |
| `entity` | string | No | - | Filter by entity name (partial match) |
| `from_date` | date (ISO 8601) | No | - | Articles published on or after this date |
| `to_date` | date (ISO 8601) | No | - | Articles published on or before this date |
| `include_full_text` | boolean | No | false | Include full article text in response |
| `page` | integer | No | 1 | Page number (1-indexed) |
| `page_size` | integer | No | 20 | Results per page (max: 100) |
| `sort` | string | No | relevance | Sort by: `relevance`, `published_date` |
| `order` | string | No | desc | Sort order: `asc` or `desc` |

**Response Schema (200 OK):**
```json
{
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "url": "https://jamaica-gleaner.com/article/...",
      "title": "Government Minister Under Investigation",
      "section": "news",
      "published_date": "2024-01-15T10:30:00Z",
      "news_source": "JAMAICA_GLEANER",
      "snippet": "...highlighted excerpt with <mark>search terms</mark>...",
      "entities": ["John Smith", "Ministry of Finance"],
      "classifications": [
        {
          "classifier_type": "CORRUPTION",
          "confidence": 0.92
        }
      ],
      "full_text": "..." // Only if include_full_text=true
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_results": 150,
    "total_pages": 8
  },
  "query": {
    "q": "corruption",
    "from_date": "2024-01-01",
    "to_date": null,
    "entity": null
  }
}
```

**Error Responses:**
- `400 Bad Request` - Invalid query parameters (bad date format, page < 1, etc.)
- `500 Internal Server Error` - Database/server errors

---

## Database Requirements

### New Index for Full-Text Search
A new migration will be needed to add a GIN index for PostgreSQL FTS:

```sql
-- Add tsvector column for full-text search
ALTER TABLE articles ADD COLUMN search_vector tsvector;

-- Populate search_vector from title and full_text
UPDATE articles SET search_vector =
  setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
  setweight(to_tsvector('english', coalesce(full_text, '')), 'B');

-- Create GIN index for fast FTS queries
CREATE INDEX idx_articles_search_vector ON articles USING GIN(search_vector);

-- Trigger to keep search_vector updated
CREATE FUNCTION articles_search_vector_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector :=
    setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.full_text, '')), 'B');
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER articles_search_vector_trigger
  BEFORE INSERT OR UPDATE ON articles
  FOR EACH ROW EXECUTE FUNCTION articles_search_vector_update();
```

### Existing Indexes (Already in place)
- `idx_articles_published_date` - Supports date range queries
- `idx_classifications_article_id` - Supports classification JOIN queries
- Entity queries will JOIN through `article_entities` and `entities` tables

---

## Files to Create/Modify

1. **`openapi/article-search.yaml`** - OpenAPI 3.0 specification with:
   - Search endpoint definition
   - Request/response schemas
   - Error schemas
   - Example requests/responses

2. **`src/article_persistence/models/domain.py`** - Add `NewsSourceType` enum:
   ```python
   class NewsSourceType(str, Enum):
       """Type-safe identifier for news sources in API responses."""
       JAMAICA_GLEANER = "JAMAICA_GLEANER"
       # Future: JAMAICA_OBSERVER = "JAMAICA_OBSERVER"
   ```
   Pattern follows existing `ClassifierType` enum in `src/services/article_classification/models.py`.

---

## Implementation Notes

### PostgreSQL Full-Text Search Query
```sql
SELECT a.public_id, a.url, a.title, a.section, a.published_date,
       ns.id as news_source_id,
       ts_headline('english', a.full_text, query, 'MaxWords=30, MinWords=15') as snippet,
       COALESCE(
         json_agg(
           json_build_object(
             'classifier_type', c.classifier_type,
             'confidence', c.confidence_score
           )
         ) FILTER (WHERE c.id IS NOT NULL),
         '[]'
       ) as classifications
FROM articles a
CROSS JOIN plainto_tsquery('english', :search_term) query
JOIN news_sources ns ON a.news_source_id = ns.id
LEFT JOIN classifications c ON a.id = c.article_id
WHERE a.search_vector @@ query
  AND (:from_date IS NULL OR a.published_date >= :from_date)
  AND (:to_date IS NULL OR a.published_date <= :to_date)
GROUP BY a.id, a.public_id, a.url, a.title, a.section, a.published_date, a.full_text, ns.id, query
ORDER BY ts_rank(a.search_vector, query) DESC
LIMIT :page_size OFFSET :offset;
```

**Note:** The `news_source_id` is mapped to `NewsSourceType` enum in the application layer:
- `news_source_id = 1` → `"JAMAICA_GLEANER"`

### Entity Filter Query (addition)
```sql
-- Add JOIN for entity filtering
LEFT JOIN article_entities ae ON a.id = ae.article_id
LEFT JOIN entities e ON ae.entity_id = e.id
WHERE (:entity IS NULL OR e.name ILIKE '%' || :entity || '%')
```

---

## Verification Plan
1. Validate OpenAPI spec at editor.swagger.io
2. Test SQL queries against existing article data
3. Verify index performance with EXPLAIN ANALYZE
