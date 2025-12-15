# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python backend project called "jaacountable-backend" that implements a news-gathering system focused on Jamaica Gleaner newspaper. The project uses Google ADK (Agent Development Kit) to create LLM agents that scrape and analyze news articles for government accountability topics.

## Key Architecture

### Core Components

- **Main Entry Point**: `main.py` - Simple entry point with basic "Hello World" functionality
- **Article Discovery**: `src/article_discovery/` - RSS-based article discovery system
  - `discoverers/gleaner_rss_discoverer.py` - Multi-feed RSS discoverer for Jamaica Gleaner
  - `models.py` - Discovery models (`RssFeedConfig`, `DiscoveredArticle`)
  - `base.py` - Protocol definition for article discovery
- **Agent System**: `gleaner_researcher_agent/` - Contains the LLM agent implementation
  - `agent.py` - Defines the `news_gatherer_agent` using Google ADK's LlmAgent with LiteLLM model (o4-mini)
  - `tools.py` - Web scraping tools for Jamaica Gleaner sections (lead stories and news)
  - `v1.evalset.json` - Evaluation dataset for testing agent performance
- **Database Layer**: PostgreSQL-based persistence layer
  - `config/database.py` - asyncpg connection pool manager
  - `alembic/` - Database migration system with manual SQL DDL
  - `alembic/versions/` - Migration files with raw SQL
  - `scripts/` - Helper scripts for database operations

### Agent Architecture

The system uses a single specialized agent (`news_gatherer_agent`) that:
- Scrapes two specific Jamaica Gleaner sections: lead stories and news
- Identifies articles relevant to government accountability
- Returns structured JSON responses with relevance scoring
- Implements respectful crawling with 10-second delays

### Article Discovery System

The RSS-based article discovery system uses a multi-feed architecture that supports discovering articles from multiple RSS feeds simultaneously.

**Key Features:**
- **Multi-Feed Support**: Processes multiple RSS feeds in a single discovery operation
- **Per-Feed Sections**: Each feed can map to a different section (e.g., "lead-stories", "news")
- **Cross-Feed Deduplication**: Automatically deduplicates articles that appear in multiple feeds
- **Fail-Soft Error Handling**: If one feed fails, continues processing remaining feeds
- **Retry Logic**: Exponential backoff retry logic for network failures

**Components:**
- `GleanerRssFeedDiscoverer`: Main discoverer class that processes multiple feeds
- `RssFeedConfig`: Configuration dataclass for feed URL + section mapping
- `DiscoveredArticle`: Model for discovered article metadata (URL, title, section, dates)

**Usage Example:**
```python
from src.article_discovery.discoverers.gleaner_rss_discoverer import GleanerRssFeedDiscoverer
from src.article_discovery.models import RssFeedConfig

# Configure multiple feeds
feed_configs = [
    RssFeedConfig(
        url="https://jamaica-gleaner.com/feed/rss.xml",
        section="lead-stories"
    ),
    RssFeedConfig(
        url="https://jamaica-gleaner.com/feed/news.xml",
        section="news"
    )
]

# Discover articles from all feeds
discoverer = GleanerRssFeedDiscoverer(feed_configs=feed_configs)
articles = await discoverer.discover(news_source_id=1)
```

**Important Design Notes:**
- Feed URLs are passed as constructor parameters (not stored in database)
- Articles are deduplicated by URL across all feeds (first occurrence kept)
- Each feed is processed sequentially (not concurrently) to respect rate limits
- Discovery happens BEFORE extraction and classification
- No `article_id` at discovery stage (articles not yet stored)

**Testing:**
- Unit tests: `tests/article_discovery/discoverers/test_gleaner_rss_discoverer.py` (21 tests)
- Validation script: `scripts/validate_rss_discovery.py`

### Dependencies

**Agent System:**
- `google-adk>=1.8.0` - Google Agent Development Kit for LLM agent framework
- `litellm>=1.74.3` - LLM abstraction layer, configured to use o4-mini model
- `requests` - HTTP library for web scraping

**Database Layer:**
- `alembic>=1.17.1` - Database migration management
- `asyncpg>=0.30.0` - Async PostgreSQL driver
- `aiosql>=13.4` - SQL query management with raw SQL
- `greenlet>=3.2.3` - Required for SQLAlchemy async operations
- `pydantic>=2.11.7` - Data validation and serialization

**Environment:**
- Python 3.12+ required
- Docker & Docker Compose for local PostgreSQL database

## Development Commands

### Running the Application

The README indicates the project can be run via:
```bash
adk web
```

This suggests the project is designed to work with Google ADK's web interface.

### Database Management

**Helper Scripts** (all located in `scripts/`):
- `./scripts/start-db.sh` - Start PostgreSQL Docker container and wait for health check
- `./scripts/migrate.sh` - Run Alembic migrations to latest version
- `./scripts/create-migration.sh "message"` - Create new migration file with manual SQL DDL

**Common Operations:**
```bash
# Start database
./scripts/start-article_persistence.sh

# Run migrations
./scripts/migrate.sh

# Create new migration
./scripts/create-migration.sh "add classifications table"

# Connect to database
docker exec -it postgres psql -U user -d jaacountable_db

# View logs
docker-compose logs postgres

# Stop database
docker-compose down

# Stop and remove data (DESTRUCTIVE)
docker-compose down -v
```

**Database Credentials** (local development):
- User: `user`
- Password: `password`
- Database: `jaacountable_db`
- Port: `5432`
- Connection string: `postgresql+asyncpg://user:password@localhost:5432/jaacountable_db`

### Package Management

The project uses `uv` for dependency management:
- `uv.lock` - Lock file for reproducible builds
- `pyproject.toml` - Project configuration and dependencies

### Testing

The project uses pytest with testcontainers for isolated database testing. Each test session spins up a fresh PostgreSQL container and runs migrations automatically.

#### Test Categories

**Unit Tests:**
- Use mocks to simulate LLM responses
- No actual API calls made
- Fast execution
- Run by default during local development

**Integration Tests:**
- Make actual LLM API calls to validate end-to-end functionality
- Require `OPENAI_API_KEY` in `.env` file
- Slower execution and incur API costs
- Marked with `@pytest.mark.integration`
- Run during CI to ensure classifier works correctly

#### Running Tests

**Run all tests (unit + integration):**
```bash
uv run pytest tests/
```

**Run only unit tests (skip integration - no LLM API calls):**
```bash
uv run pytest tests/ -m "not integration"
```

**Run only integration tests (requires API key):**
```bash
uv run pytest tests/ -m integration
```

**Run tests with verbose output:**
```bash
uv run pytest tests/ -v
```

**Run tests with logging (shows database connection details):**
```bash
uv run pytest tests/ -v --log-cli-level=INFO
```

**Run a specific test file:**
```bash
uv run pytest tests/services/article_classification/test_corruption_classifier.py -v
```

**Run a specific test class:**
```bash
uv run pytest tests/article_persistence/repositories/test_article_repository.py::TestInsertArticleHappyPath -v
```

**Parallel Test Execution:**

The project includes pytest-xdist for running tests in parallel. Due to session-scoped async database fixtures, parallel execution works best across different test files:

```bash
# Run test files in parallel (each file runs in its own worker)
uv run pytest tests/ -n auto --dist loadfile

# Run only unit tests in parallel (skip integration)
uv run pytest tests/ -n auto --dist loadfile -m "not integration"
```

#### Test Features

- **Automatic PostgreSQL container lifecycle management**
- **Alembic migrations run automatically on test database**
- **Transaction rollback after each test for isolation**
- **BDD-style test format** (Given/When/Then comments)
- **Tests organized into classes by category** (HappyPath, ValidationErrors, DatabaseConstraints, EdgeCases)
- **pytest-xdist** available for parallel test execution across multiple test files
- **Integration test markers** registered in `pyproject.toml` for selective test execution

#### CI/CD

GitHub Actions CI runs **all tests** (including integration tests) using the `CLASSIFIER_AGENTS_CI` secret for the API key. This ensures the classifier works correctly with real LLM calls before merging.

**Test Infrastructure:**
- `tests/conftest.py` - Pytest fixtures for database testing
- `testcontainers` - Spins up isolated PostgreSQL containers per test session
- Automatic Alembic migrations on test database
- Transaction rollback after each test for isolation
- BDD-style test format (Given/When/Then comments)
- Tests organized into classes by category (e.g., `TestInsertArticleHappyPath`, `TestInsertArticleValidationErrors`)
- pytest-xdist for parallel test execution across test files

**Available Fixtures:**
- `postgres_container` - Session-scoped PostgreSQL container
- `test_database_url` - Connection URL from container
- `run_migrations` - Runs Alembic migrations on test database
- `db_pool` - asyncpg connection pool
- `db_connection` - Connection with automatic transaction rollback

Note: Tests within a single file run sequentially due to session-scoped async database fixtures and event loop constraints with pytest-asyncio.

The project also includes an evaluation set (`v1.evalset.json`) for testing agent performance.

## Important Implementation Details

### Database Architecture
- **Raw SQL Approach**: Uses manual SQL DDL in Alembic migrations, NOT SQLAlchemy ORM models
- **Async Operations**: All database operations use asyncpg for async/await patterns
- **Connection Pooling**: `config/database.py` manages connection pools with proper lifecycle
- **Query Management**: Future queries will use aiosql with SQL stored in `.sql` files
- **Migration Strategy**: All migrations include both `upgrade()` and `downgrade()` functions
- **Environment Config**: Database URL loaded from `.env` file, managed by Alembic
- **UTC Timestamps**: All timestamp columns use `TIMESTAMPTZ` and Python code uses `datetime.now(timezone.utc)` for timezone-aware UTC datetimes

**Current Schema:**
- `articles` table: Stores scraped articles with deduplication via unique URL constraint
  - Indexes on `url` and `published_date` for performance
  - `fetched_at` (TIMESTAMPTZ) tracks when article was scraped
  - `published_date` (TIMESTAMPTZ) stores article publication date
  - `full_text` stores complete article content for classification

### Web Scraping Ethics
- The scraping tools implement a 10-second crawl delay to respect the target website
- Uses appropriate User-Agent headers
- Focuses only on two specific sections to minimize load

### Agent Prompt Engineering
- The agent is specifically instructed to look for government accountability topics
- Returns structured JSON with relevance scoring (1-10)
- Limited to maximum 20 articles per run to prevent overwhelming downstream systems
- Includes specific keywords and criteria for identifying relevant articles

### Data Flow
1. Agent calls `get_gleaner_lead_stories()` and `get_gleaner_news_section()`
2. Tools fetch HTML content with crawl delays
3. Agent processes content using LLM to identify relevant articles
4. Returns structured JSON with article metadata and relevance scores
5. (Future) Articles stored in PostgreSQL via asyncpg for persistence and deduplication

### Classification System Architecture

The project includes a modular classification system for AI-based article analysis. This system is separate from the initial news gathering agent and focuses on determining article relevance to specific accountability topics.

**Key Design Principles:**
- **Separation of Concerns**: Classification schemas (agent I/O) are separate from database models (persistence)
- **Classification Before Storage**: Articles are classified BEFORE database storage, so `article_id` is not available during classification
- **Type-Safe Classifier Identification**: Uses `ClassifierType` enum for type safety and JSON serialization
- **Comprehensive Validation**: Pydantic v2 models with extensive field validators
- **Extensible**: New classifiers can be added by extending the `ClassifierType` enum

**Classification Workflow:**
```
Extract → ClassificationInput → Classifier Agent → ClassificationResult → Store if relevant (article_id generated)
```

**Core Models (`src/services/article_classification/models.py`):**

1. **`ClassifierType` enum** (lines 7-24):
   - First enum in codebase using `(str, Enum)` pattern for JSON serialization
   - Type-safe classifier identification
   - Current values: `CORRUPTION`, `HURRICANE_RELIEF`
   - Add new classifiers by extending this enum

2. **`ClassificationInput` model** (lines 27-125):
   - Interface between extraction and classification layers
   - 5 fields: `url`, `title`, `section`, `full_text`, `published_date`
   - **Important**: No `article_id` field (classification happens before storage)
   - Validators for URL format, minimum text length (50 chars), timezone-aware datetimes
   - Constructed from `ExtractedArticleContent` + scraper context

3. **`ClassificationResult` model** (lines 128-199):
   - Structured output from classifier agents
   - 6 fields: `is_relevant`, `confidence`, `reasoning`, `key_entities`, `classifier_type`, `model_name`
   - `key_entities` defaults to `[]` (not `None`) for better ergonomics
   - `confidence` validated between 0.0 and 1.0
   - `model_name` included for traceability (tracks which LLM produced the result)
   - Validators for all fields with whitespace stripping and entity cleaning

**Test Coverage (`tests/services/article_classification/test_models.py`):**
- 62 total tests, all following BDD-style (Given/When/Then) format
- TestClassificationInputValidation: 25 tests
- TestClassifierTypeEnum: 5 tests
- TestClassificationResultValidation: 32 tests
- All tests use async pattern with pytest-asyncio
- Comprehensive validation testing, boundary conditions, edge cases (Unicode, very long text)

**Adding a New Classifier:**

1. **Update `ClassifierType` enum:**
   ```python
   class ClassifierType(str, Enum):
       CORRUPTION = "CORRUPTION"
       HURRICANE_RELIEF = "HURRICANE_RELIEF"
       NEW_CLASSIFIER = "NEW_CLASSIFIER"  # Add here
   ```

2. **Add enum test** in `TestClassifierTypeEnum`:
   ```python
   async def test_classifier_type_new_classifier_succeeds(self):
       result = ClassificationResult(
           is_relevant=True,
           confidence=0.85,
           reasoning="Test reasoning",
           classifier_type=ClassifierType.NEW_CLASSIFIER,
           model_name="gpt-4o-mini",
       )
       assert result.classifier_type == ClassifierType.NEW_CLASSIFIER
   ```

3. **Implement classifier agent** that accepts `ClassificationInput` and returns `ClassificationResult`

4. **Write comprehensive tests** for the new classifier agent

5. **Update database schema** if needed (create migration for classifier-specific columns)

**Important Notes:**
- Classification models use Pydantic v2 with `ConfigDict(from_attributes=True)`
- All validators use `@field_validator` decorator (Pydantic v2 pattern)
- Python 3.12+ type hints: `str | None` instead of `Optional[str]`
- `key_entities` uses list cleaning validator (strips whitespace, filters empty strings)
- All timestamp fields must be timezone-aware (`datetime.now(timezone.utc)`)
- First enum in codebase - established `(str, Enum)` pattern for JSON serialization

**Related Models:**
- `src/services/article_extractor/models.py` - `ExtractedArticleContent` (input to classification)
- `src/db/models/domain.py` - Database models for persistence (separate from classification schemas)