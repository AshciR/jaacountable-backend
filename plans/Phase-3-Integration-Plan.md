# Phase 3 Integration Plan: Article Discovery → Classification → Persistence

## Executive Summary

Integrate three existing stable components into a production-ready orchestrator:
- **Article Extractor** → `ExtractedArticleContent`
- **Article Classification** → `List[ClassificationResult]`
- **Article Persistence** → Database storage

## Architecture Overview

```
URL Discovery → Extraction → Classification → Relevance Filter → Storage
     ↓              ↓              ↓                ↓              ↓
Discover URLs   Extract      Classify for    Filter by       Store article
from section    full text    relevance    confidence>=0.7  + classifications
    pages                    (parallel)
```

## Key Design Decisions

1. **Separate seeding + daily orchestrator**: Two distinct code paths for historical vs ongoing
2. **New discovery service**: Scrapes Jamaica Gleaner section pages to find article URLs
3. **Store only relevant**: Articles must have `is_relevant=True` AND `confidence >= 0.7`
4. **Resilient error handling**: Continue on extraction failures, retry with exponential backoff
5. **Transaction per article**: Isolation and atomicity for each article + classifications

---

## Components to Build

### 1. Article Discovery Service (NEW)

**Location:** `src/article_discovery/`

**Purpose:** Scrape Jamaica Gleaner section pages to extract article URLs

**Files:**
- `models.py` - `DiscoveredArticle`, `DiscoverySection` enum
- `base.py` - `ArticleDiscovery` Protocol
- `gleaner_discovery.py` - `GleanerArticleDiscovery` implementation
- `service.py` - `ArticleDiscoveryService` (strategy pattern)

**Key Interface:**
```python
class ArticleDiscoveryService:
    async def discover_articles_from_sections(
        sections: list[DiscoverySection],
        news_source: str = "jamaica-gleaner",
        max_articles_per_section: int | None = None
    ) -> list[DiscoveredArticle]
```

**Implementation Details:**
- Respects 10-second crawl delay between sections
- Parses HTML to find `<a>` tags containing `/article/` in href
- Deduplicates URLs (section pages may list same article multiple times)
- Returns `DiscoveredArticle(url, section, discovered_at)`

---

### 2. Model Converters (NEW)

**Location:** `src/orchestration/converters.py`

**Purpose:** Bridge service models and database domain models

**Functions:**

```python
def extracted_content_to_classification_input(
    extracted: ExtractedArticleContent,
    url: str,
    section: DiscoverySection
) -> ClassificationInput

def extracted_content_to_article(
    extracted: ExtractedArticleContent,
    url: str,
    section: DiscoverySection,
    news_source_id: int
) -> Article

def classification_result_to_classification(
    result: ClassificationResult,
    article_id: int
) -> Classification

def filter_relevant_classifications(
    results: list[ClassificationResult],
    min_confidence: float = 0.7
) -> list[ClassificationResult]
```

**Critical Logic:**
- `filter_relevant_classifications`: Returns only results where `is_relevant=True` AND `confidence >= threshold`
- Empty list means article should NOT be stored

---

### 3. Daily Orchestrator Service (NEW)

**Location:** `src/orchestration/`

**Files:**
- `config.py` - `OrchestratorConfig` (environment-based configuration)
- `daily_orchestrator.py` - `DailyOrchestratorService`

**Main Workflow:**
```python
class DailyOrchestratorService:
    async def run_daily_pipeline(
        sections: list[DiscoverySection] | None = None
    ) -> dict[str, Any]:
        # 1. Discover article URLs
        discovered = await self._discover_articles(sections)

        # 2. For each discovered article:
        for discovered in discovered_articles:
            # 2a. Extract content (with retry)
            extracted = await self._extract_with_retry(url)

            # 2b. Classify (with retry, runs all classifiers in parallel)
            results = await self._classify_with_retry(classification_input)

            # 2c. Filter relevant (confidence >= threshold)
            relevant = filter_relevant_classifications(results, min_confidence=0.7)

            # 2d. Store if relevant (transaction per article)
            if relevant:
                await self._store_with_retry(extracted, discovered, relevant)
```

**Transaction Strategy:**
```python
async with db_config.connection() as conn:
    async with conn.transaction():
        # Insert article (get article_id)
        stored_article = await article_repo.insert_article(conn, article)

        # Insert all relevant classifications
        for result in relevant_results:
            classification = classification_result_to_classification(
                result, stored_article.id
            )
            await classification_repo.insert_classification(conn, classification)
```

**Error Handling:**
- **Discovery failure**: Retry with exponential backoff, fail if max retries exceeded
- **Extraction failure**: Log error, skip article, continue with next
- **Classification failure**: Log error, skip article, continue with next
- **Duplicate article** (`UniqueViolationError`): Log info, skip gracefully
- **Storage failure**: Retry with exponential backoff

**Retry Logic:**
- `delay = base_delay * (2 ** attempt)` (exponential backoff)
- Default: max 3 attempts, base delay 2 seconds
- Applied to: discovery, extraction, classification, storage

**Configuration (Environment Variables):**
```python
MIN_CONFIDENCE_THRESHOLD=0.7
MAX_ARTICLES_PER_SECTION=50
JAMAICA_GLEANER_NEWS_SOURCE_ID=1
RETRY_MAX_ATTEMPTS=3
RETRY_BASE_DELAY_SECONDS=2
```

---

### 4. Historical Seeding Script (NEW)

**Location:** `scripts/`

**Files:**
- `utils/progress_tracker.py` - `ProgressTracker` for resume capability
- `seed_historical_articles.py` - Main seeding script

**Purpose:** Backfill 4 years of historical articles

**Progress Tracking:**
- Saves state to `seed_progress.json` after every 10 URLs
- Tracks processed URLs to avoid reprocessing
- Can resume from interrupted runs
- Shows progress summary

**Usage:**
```bash
# Initial run
python scripts/seed_historical_articles.py --start-date 2021-12-01 --end-date 2025-12-01

# Resume interrupted run
python scripts/seed_historical_articles.py --resume
```

**Important Note:**
POC implementation uses daily pipeline. True historical seeding requires:
- Archive page scraping (if Jamaica Gleaner has date archives)
- Sitemap parsing (if available)
- Date-based URL construction
Future enhancement post-POC.

---

## Data Flow Diagram

```
1. DISCOVERY
   ArticleDiscoveryService.discover_articles_from_sections()
      ↓
   List[DiscoveredArticle(url, section, discovered_at)]

2. EXTRACTION
   For each DiscoveredArticle:
      ArticleExtractionService.extract_article_content(url)
         ↓
      ExtractedArticleContent(title, full_text, author, published_date)

3. CLASSIFICATION INPUT
   extracted_content_to_classification_input(extracted, url, section)
      ↓
   ClassificationInput(url, title, section, full_text, published_date)

4. CLASSIFICATION
   ClassificationService.classify(classification_input)
      ↓
   List[ClassificationResult] (from all classifiers in parallel)

5. RELEVANCE FILTER
   filter_relevant_classifications(results, min_confidence=0.7)
      ↓
   List[ClassificationResult] (only relevant with confidence >= 0.7)
      ↓
   if empty: SKIP article (don't store)
      ↓
   if not empty: CONTINUE to storage

6. STORAGE (Transaction per article)
   a. extracted_content_to_article(extracted, url, section, news_source_id)
         ↓
      Article domain model

   b. ArticleRepository.insert_article(conn, article)
         ↓
      Article with article_id

   c. For each relevant ClassificationResult:
         classification_result_to_classification(result, article_id)
            ↓
         Classification domain model

         ClassificationRepository.insert_classification(conn, classification)
            ↓
         Stored classification
```

---

## Critical Files to Create

### New Directories
1. `/Users/richie/Development/python/jaacountable-backend/src/article_discovery/`
2. `/Users/richie/Development/python/jaacountable-backend/src/orchestration/`
3. `/Users/richie/Development/python/jaacountable-backend/scripts/utils/`

### New Files (Priority Order)

**Phase 3A: Discovery (2-3 hours)**
1. `src/article_discovery/__init__.py`
2. `src/article_discovery/models.py` - DiscoveredArticle, DiscoverySection
3. `src/article_discovery/base.py` - ArticleDiscovery Protocol
4. `src/article_discovery/gleaner_discovery.py` - GleanerArticleDiscovery
5. `src/article_discovery/service.py` - ArticleDiscoveryService
6. `tests/article_discovery/test_gleaner_discovery.py` - Unit tests with mocked HTML

**Phase 3B: Converters (1 hour)**
1. `src/orchestration/__init__.py`
2. `src/orchestration/converters.py` - All conversion functions
3. `tests/orchestration/test_converters.py` - Unit tests for converters

**Phase 3C: Orchestrator (3-4 hours)**
1. `src/orchestration/config.py` - OrchestratorConfig
2. `src/orchestration/daily_orchestrator.py` - DailyOrchestratorService
3. `tests/orchestration/test_daily_orchestrator_unit.py` - Unit tests with mocks
4. `tests/orchestration/test_daily_orchestrator_integration.py` - E2E integration test

**Phase 3D: Seeding Script (2-3 hours)**
1. `scripts/utils/__init__.py`
2. `scripts/utils/progress_tracker.py` - ProgressTracker
3. `scripts/seed_historical_articles.py` - CLI script with argparse
4. `tests/scripts/test_progress_tracker.py` - Unit tests

**Phase 3E: Documentation (1 hour)**
1. Update `CLAUDE.md` with orchestration documentation
2. Update `README.md` with usage examples
3. Add troubleshooting guide

---

## Implementation Order (10-13 hours)

### Phase 3A: Discovery Service (2-3 hours)
- Create models (DiscoveredArticle, DiscoverySection enum)
- Implement GleanerArticleDiscovery (HTML parsing, crawl delay)
- Write tests with mocked HTML responses
- Manual test against live Jamaica Gleaner

### Phase 3B: Model Converters (1 hour)
- Implement all 4 conversion functions
- Write unit tests for each converter
- Test enum conversions and edge cases

### Phase 3C: Daily Orchestrator (3-4 hours)
- Create OrchestratorConfig with environment loading
- Implement DailyOrchestratorService workflow
- Add retry logic with exponential backoff
- Add transaction handling per article
- Write unit tests with mocked services
- Write integration test with real database

### Phase 3D: Historical Seeding Script (2-3 hours)
- Implement ProgressTracker for resume capability
- Create CLI script with argparse
- Add progress reporting
- Write tests for progress tracking

### Phase 3E: Documentation & Testing (1 hour)
- Update CLAUDE.md
- Add usage examples
- Run full test suite
- Manual E2E testing

---

## Testing Strategy

### Unit Tests (Fast, No External Dependencies)
- **Discovery**: Mock HTTP responses with sample HTML
- **Converters**: Test model field mappings and edge cases
- **Orchestrator**: Mock all services (discovery, extraction, classification, persistence)
- **Progress Tracker**: Test state save/load/resume logic

### Integration Tests (Slow, Real Database + Mocked HTTP/LLM)
- **E2E Pipeline**: Real database, mocked HTTP scraping, mocked LLM calls
- Verify full workflow: discover → extract → classify → store
- Test duplicate handling (UniqueViolationError)
- Test relevance filtering (only store articles with confidence >= 0.7)
- Verify transaction rollback on errors

### Test Coverage Target
- 80%+ coverage for new code
- All critical paths tested (happy path + error cases)
- BDD-style organization (Given/When/Then)

---

## Key Implementation Details

### Discovery HTML Parsing Strategy
```python
# Find all <a> tags with href containing "/article/"
for link in soup.find_all("a", href=True):
    href = link["href"]
    if "/article/" in href:
        absolute_url = urljoin(self.base_url, href)
        if absolute_url not in article_links:
            article_links.append(absolute_url)
```

### Relevance Filter Logic
```python
def filter_relevant_classifications(results, min_confidence=0.7):
    return [
        result
        for result in results
        if result.is_relevant and result.confidence >= min_confidence
    ]

# Article is stored ONLY if filter_relevant_classifications returns non-empty list
```

### Transaction Boundary
```python
# ONE transaction per article (isolation)
async with conn.transaction():
    # 1. Insert article
    stored_article = await article_repo.insert_article(conn, article)

    # 2. Insert ALL relevant classifications
    for result in relevant_results:
        classification = classification_result_to_classification(result, stored_article.id)
        await classification_repo.insert_classification(conn, classification)

    # Commit happens here (end of context manager)
```

### Duplicate Handling
```python
try:
    stored_article = await article_repo.insert_article(conn, article)
except UniqueViolationError:
    # Article already exists (URL unique constraint)
    logger.info(f"Article already exists, skipping: {url}")
    return  # Not an error, just skip
```

### Retry with Exponential Backoff
```python
attempt = 0
while attempt < max_attempts:
    try:
        return await operation()
    except Exception as e:
        attempt += 1
        if attempt >= max_attempts:
            raise

        delay = base_delay_seconds * (2 ** attempt)
        logger.warning(f"Attempt {attempt} failed, retrying in {delay}s: {e}")
        await asyncio.sleep(delay)
```

---

## Success Criteria

### Functional
- [ ] Discovery service extracts URLs from Jamaica Gleaner sections
- [ ] Daily orchestrator completes E2E flow: discover → classify → store
- [ ] Only articles with `is_relevant=True` AND `confidence >= 0.7` are stored
- [ ] Duplicate articles handled gracefully (skip, not error)
- [ ] Seeding script has resume capability

### Non-Functional
- [ ] Respects 10-second crawl delay
- [ ] Retry logic with exponential backoff
- [ ] Transaction per article (atomicity)
- [ ] Test coverage >= 80%
- [ ] All integration tests pass

### Documentation
- [ ] CLAUDE.md updated with orchestration info
- [ ] README has usage examples
- [ ] Environment variables documented
- [ ] Troubleshooting guide available

---

## Environment Variables (.env)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/jaacountable_db

# Classification (LLM API)
OPENAI_API_KEY=sk-your-key-here

# Orchestrator
MIN_CONFIDENCE_THRESHOLD=0.7
MAX_ARTICLES_PER_SECTION=50
JAMAICA_GLEANER_NEWS_SOURCE_ID=1

# Retry
RETRY_MAX_ATTEMPTS=3
RETRY_BASE_DELAY_SECONDS=2

# Logging
LOG_LEVEL=INFO
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Jamaica Gleaner HTML changes | Add structure validation in tests, log warnings, fallback selectors |
| LLM API rate limits | Retry with backoff, catch failures (don't crash pipeline) |
| Database connection pool exhaustion | Proper pool config, context managers, monitor stats |
| Historical seeding too slow | Progress tracking + resume, batch processing |
| Duplicate detection fails | Database UNIQUE constraint as safety net, explicit tests |

---

## Future Enhancements (Post-POC)

1. **Parallel article processing** - Process multiple articles concurrently
2. **Archive/sitemap parsing** - True historical seeding for 4-year backfill
3. **Incremental discovery** - Only discover articles since last run
4. **Classification caching** - Avoid re-classifying same article
5. **Monitoring & alerting** - Prometheus metrics, failure rate alerts
6. **Performance optimization** - Batch database inserts, connection pool tuning

---

## Summary

This plan provides a complete, actionable roadmap for Phase 3 integration. Key highlights:

- **4 new components**: Discovery, Converters, Orchestrator, Seeding Script
- **~15 new files** to create across 3 phases
- **10-13 hours** total implementation time
- **Modular design**: Each component independently testable
- **Resilient**: Graceful error handling, retry logic, transaction safety
- **Observable**: Structured logging throughout
- **Extensible**: Easy to add classifiers or news sources

The orchestrator treats existing components (extractor, classifier, persistence) as stable APIs and focuses on integration, error handling, and workflow orchestration.
