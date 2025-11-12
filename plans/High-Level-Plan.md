# Implementation Plan: Jaacountable Backend

## Overview
Transform the current single-agent news gathering system into a full-stack backend with database persistence, multi-agent classification, and RESTful API.

**Tech Stack:** PostgreSQL + aiosql + asyncpg + Alembic + FastAPI + Google ADK multi-agent orchestration

**Development Approach:** Agile/Iterative - Each phase includes Development, Testing, and Documentation

---

## Phase 1: Database Foundation (3-4 hours)
**Goal:** Set up PostgreSQL database with aiosql queries and Alembic migrations

### Development (1.5-2 hours)
1. **Add database dependencies**
   - aiosql (>=12.2) - SQL query management
   - asyncpg (>=0.30.0) - Async PostgreSQL driver
   - alembic (>=1.14.0) - Database migrations
   - pydantic (>=2.10.0) - Data validation
   - pydantic-settings (>=2.7.0) - Configuration management

2. **Set up Alembic**
   - Initialize Alembic: `alembic init alembic`
   - Configure alembic.ini for asyncpg connection
   - Create initial migration with raw SQL for tables:
     - `articles`: id, url (unique), title, section, published_date, fetched_at, full_text
     - `classifications`: id, article_id (FK), classifier_type, is_relevant, confidence_score, reasoning, classified_at
     - `sources`: id, name, base_url, last_scraped_at
   - Add indexes on url, published_date, classifier_type

3. **Create SQL queries** (`db/queries/`)
   - `articles.sql` - CRUD operations:
     - `-- name: insert_article<!` - Insert article, return id
     - `-- name: get_article^` - Get by id
     - `-- name: get_article_by_url^` - Check if exists
     - `-- name: list_articles` - List with filters
   - `classifications.sql` - CRUD operations:
     - `-- name: insert_classification<!`
     - `-- name: get_classifications_by_article$`
     - `-- name: list_classifications_by_type`
   - `sources.sql` - CRUD operations

4. **Create database configuration** (`config/database.py`)
   - AsyncPG connection pool setup
   - Load aiosql queries from .sql files
   - Environment-based connection string (DATABASE_URL)
   - Context manager for database connections

5. **Create Pydantic models** (`models/domain.py`)
   - `Article` - For validation/serialization (NOT ORM)
   - `Classification` - For validation/serialization
   - `Source` - For validation/serialization

### Testing (1 hour)
- Set up pytest with pytest-asyncio
- Create test database fixture (separate test DB)
- Unit tests for all aiosql queries:
  - Test insert operations
  - Test select operations
  - Test deduplication (insert duplicate URL)
  - Test foreign key constraints
- Test connection pool management
- Test Alembic migrations (upgrade/downgrade)

### Documentation (30 min)
- Database schema diagram/description
- Environment variable setup guide (DATABASE_URL format)
- Migration commands:
  - `alembic upgrade head` - Apply migrations
  - `alembic downgrade -1` - Rollback last migration
- Example usage of aiosql queries in code

**Deliverable:** Fully tested database layer with migrations and async queries

---

## Phase 2: Classification Agents (3-4 hours)
**Goal:** Build and test specialized classifier agents for corruption and hurricane relief

### Development (1.5-2 hours)
1. **Create corruption classifier** (`corruption_classifier_agent/`)
   - `agent.py` - LlmAgent using o4-mini model
   - Prompt engineering to identify:
     - Embezzlement, bribery, fraud
     - Misuse of public funds
     - Government official misconduct
     - Contract irregularities
   - Output schema: {is_relevant: bool, confidence: 0-1, reasoning: str, key_entities: []}

2. **Create hurricane relief classifier** (`hurricane_relief_classifier_agent/`)
   - `agent.py` - LlmAgent using o4-mini model
   - Prompt engineering to identify:
     - Hurricane/disaster relief funding
     - NEMA, ODPEM activities
     - Disaster response and reconstruction
     - Relief fund allocation and spending
   - Same output schema for consistency

3. **Create shared classification schemas** (`schemas/classification.py`)
   - Pydantic models for classifier inputs/outputs
   - `ClassifierType` enum (CORRUPTION, HURRICANE_RELIEF)
   - `ClassificationResult` model
   - `ClassificationInput` model (article data)

4. **Tool functions** (if needed)
   - Any helper functions for text processing
   - Entity extraction utilities

### Testing (1-1.5 hours)
- Create evaluation datasets:
  - `corruption_classifier_agent/v1.evalset.json` - Sample corruption articles
  - `hurricane_relief_classifier_agent/v1.evalset.json` - Sample relief articles
- Test with real Jamaica Gleaner article samples
- Unit tests for classification logic
- Validate output schema compliance (all required fields present)
- Test edge cases:
  - Non-relevant articles (sports, entertainment)
  - Ambiguous content
  - Articles mentioning both topics
- Performance/latency testing

### Documentation (30 min)
- Document classification criteria for each agent
- Provide example inputs and expected outputs
- How to run evaluations: `python test_corruption_agent.py`
- Confidence score interpretation guide
- Common false positives/negatives

**Deliverable:** Two tested, documented classifier agents with consistent output format

---

## Phase 3: Multi-Agent Orchestrator + Persistence (4-5 hours)
**Goal:** Build end-to-end pipeline from fetch → classify → persist to database

### Development (2-3 hours)
1. **Create orchestrator agent** (`orchestrator/orchestrator_agent.py`)
   - Supervisor agent using Google ADK agent composition
   - Coordinates: news_gatherer → classifiers → database
   - Manages workflow state and error handling

2. **Implement database service layer** (`services/article_service.py`)
   - Async functions using aiosql queries:
     - `save_article(article: Article) -> int` - Insert with deduplication
     - `save_classification(classification: Classification) -> int`
     - `get_articles_without_classification(classifier_type: str) -> List[Article]`
     - `article_exists_by_url(url: str) -> bool`
   - Bulk operations for efficiency
   - Transaction management

3. **Enhance news gatherer agent** (`gleaner_researcher_agent/`)
   - Refactor to extract full article text (not just metadata)
   - Parse article body content from HTML
   - Return data compatible with Article Pydantic model
   - Make callable from orchestrator

4. **Wire up orchestration workflow**
   - Step 1: Trigger news_gatherer_agent (fetch lead + news sections)
   - Step 2: Deduplicate against database (check URLs)
   - Step 3: For each new article:
     - Classify with corruption_classifier (async)
     - Classify with hurricane_relief_classifier (async)
     - Run classifiers in parallel
   - Step 4: Persist articles and classifications via aiosql
   - Add comprehensive error handling and retry logic
   - Add structured logging for observability

### Testing (1.5 hours)
- Integration tests for full pipeline:
  - Mock the news_gatherer to return test articles
  - Verify articles saved to database
  - Verify classifications saved with correct foreign keys
- Test deduplication logic:
  - Run pipeline twice with same articles
  - Verify no duplicates in database
- Test parallel classification:
  - Verify both classifiers run
  - Verify results saved correctly
- Test error scenarios:
  - Database connection failure
  - Classifier timeout/failure
  - Partial success handling
- Mock external HTTP calls for test reliability
- Test transaction rollback on errors

### Documentation (30 min)
- Pipeline architecture diagram (flowchart)
- Data flow documentation (what happens to each article)
- How to trigger orchestrator manually
- Logging and monitoring guide
- Troubleshooting common issues:
  - Classifier timeouts
  - Database connection issues
  - Duplicate article handling

**Deliverable:** Working end-to-end pipeline with verified database persistence

---

## Phase 4: FastAPI REST API (4-5 hours)
**Goal:** Build functional, tested REST API with auto-generated documentation

### Development (2-3 hours)
1. **Set up FastAPI application** (`api/main.py`)
   - Initialize FastAPI app with metadata
   - Configure CORS middleware (allow frontend origins)
   - Set up database connection pool as dependency
   - Load aiosql queries at startup
   - Configure automatic OpenAPI/Swagger documentation

2. **Create API endpoints** (`api/routes/`)
   - `articles.py`:
     - `POST /api/v1/articles/fetch` - Trigger orchestrator pipeline
     - `GET /api/v1/articles` - List articles with pagination/filtering
     - `GET /api/v1/articles/{id}` - Get single article with classifications
   - `classifications.py`:
     - `GET /api/v1/classifications` - List all classifications
     - `GET /api/v1/articles/corruption` - Articles classified as corruption
     - `GET /api/v1/articles/hurricane-relief` - Articles classified as hurricane relief
   - `health.py`:
     - `GET /api/v1/health` - Health check + database connection test

3. **Create API schemas** (`api/schemas/`)
   - Request models: `ArticleFetchRequest`, `PaginationParams`, `FilterParams`
   - Response models: `ArticleResponse`, `ArticleListResponse`, `ClassificationResponse`
   - Use Pydantic models from `models/domain.py` where applicable
   - Add examples for better API documentation

4. **Add query capabilities**
   - Pagination: offset/limit parameters
   - Filtering:
     - Date range (start_date, end_date)
     - Section (lead-stories, news)
     - Classification type
     - Minimum confidence threshold
   - Sorting: date (desc/asc), confidence score
   - Implement using aiosql queries with dynamic parameters

5. **Database dependency injection**
   - Create FastAPI dependency for database connection
   - Proper connection pool management
   - Automatic cleanup

### Testing (1.5 hours)
- API integration tests using `httpx.AsyncClient`:
  - Test all endpoints (happy path)
  - Test error cases (404, 422 validation errors)
  - Test pagination (correct offsets/limits)
  - Test filtering (date ranges, confidence thresholds)
  - Test sorting options
- Test CORS headers are present
- Test database connection in dependency injection
- Test concurrent requests (connection pool behavior)
- Basic load testing (ensure no connection leaks)
- Test OpenAPI schema generation

### Documentation (30 min)
- API usage guide with curl examples for each endpoint
- Review and enhance Swagger/OpenAPI auto-docs
- Add example requests and responses
- How to run the API locally: `uvicorn api.main:app --reload`
- Environment variables for API configuration
- API versioning strategy

**Deliverable:** Tested REST API with interactive Swagger UI at `/docs`

---

## Phase 5: API Key Authentication (2-3 hours)
**Goal:** Secure the API with tested token-based authentication

### Development (1-1.5 hours)
1. **Add API key table**
   - Create Alembic migration for `api_keys` table:
     - id, key_hash (bcrypt hash), name, created_at, last_used_at, is_active

2. **Create API key queries** (`db/queries/api_keys.sql`)
   - `-- name: insert_api_key<!` - Insert new key
   - `-- name: get_api_key_by_hash^` - Validate key
   - `-- name: update_last_used<!` - Update last_used_at
   - `-- name: list_api_keys` - List all keys (for admin)
   - `-- name: revoke_api_key!` - Soft delete (set is_active=false)

3. **Implement authentication middleware** (`api/auth.py`)
   - FastAPI dependency function for API key validation
   - Check `X-API-Key` header
   - Verify hash using passlib/bcrypt
   - Update last_used_at timestamp
   - Return 401 if invalid/missing

4. **Create admin endpoints** (`api/routes/admin.py`)
   - `POST /api/v1/admin/keys` - Generate new API key (requires master key)
   - `GET /api/v1/admin/keys` - List keys (return hashes only, not secrets)
   - `DELETE /api/v1/admin/keys/{id}` - Revoke key

5. **Add rate limiting**
   - Integrate slowapi library
   - Per-key rate limits (e.g., 100 requests/hour)
   - Return 429 Too Many Requests when exceeded

6. **Protect endpoints**
   - Add authentication dependency to all routes except `/health`
   - Ensure admin endpoints require special master key

### Testing (1 hour)
- Test API key validation:
  - Valid key → 200 OK
  - Invalid key → 401 Unauthorized
  - Missing key → 401 Unauthorized
- Test protected endpoints require authentication
- Test public endpoints (health) don't require auth
- Test admin endpoints:
  - Create key successfully
  - List keys (verify secrets not returned)
  - Revoke key (verify key stops working)
- Test rate limiting:
  - Exceed limit → 429 response
  - Different keys have separate limits
- Test key hashing security (bcrypt)
- Test last_used_at updates

### Documentation (30 min)
- How to generate initial API key (bootstrap script)
- How to use API keys in requests:
  ```bash
  curl -H "X-API-Key: your_key_here" http://localhost:8000/api/v1/articles
  ```
- Rate limiting policies and limits
- Key management best practices:
  - Rotate keys periodically
  - Use descriptive names
  - Revoke unused keys
- Security considerations

**Deliverable:** Secured API with tested authentication and rate limiting

---

## Phase 6: Docker & Deployment (2-3 hours)
**Goal:** Create production-ready containerized system

### Development (1-1.5 hours)
1. **Create Dockerfile** (`Dockerfile`)
   - Multi-stage build:
     - Stage 1: Install dependencies
     - Stage 2: Copy application code
   - Use Python 3.12 slim base image
   - Install production dependencies only
   - Set up non-root user for security
   - Expose port 8000

2. **Create docker-compose.yml**
   - Services:
     - `postgres`: PostgreSQL 16 with volume
     - `api`: FastAPI application
   - Networks and dependencies configured
   - Environment variables
   - Health checks

3. **Create deployment scripts** (`scripts/`)
   - `migrate.sh` - Run Alembic migrations
   - `start.sh` - Start Uvicorn server
   - `seed.sh` - Generate initial API key
   - `health_check.sh` - Verify API is running

4. **Environment configuration**
   - `.env.example` - Template for environment variables:
     - DATABASE_URL
     - API_HOST, API_PORT
     - CORS_ORIGINS
     - LLM_API_KEY (for Google ADK agents)
     - LOG_LEVEL
   - Production settings in `config/settings.py`

5. **Production optimizations**
   - Connection pool sizing (based on expected load)
   - Logging configuration (structured JSON logs)
   - Error tracking setup (optional: Sentry integration)
   - Graceful shutdown handling

### Testing (1 hour)
- Test Docker build: `docker build -t jaacountable-backend .`
- Test docker-compose: `docker-compose up`
- Verify both services start successfully
- Test migrations run in Docker container
- Test API accessible from host machine
- Test database persistence (data survives container restart)
- Test health check endpoint
- Test production-like environment configuration
- Load test containerized application

### Documentation (30 min)
- Deployment guide:
  - Docker deployment (recommended)
  - Manual deployment (for VPS/bare metal)
- Environment variables reference (all required vars)
- Production checklist:
  - Set secure DATABASE_URL
  - Generate strong API keys
  - Configure CORS for your domain
  - Set up SSL/TLS (reverse proxy)
  - Enable logging
  - Set up backups
- Backup and restore procedures:
  - Database backup: `pg_dump`
  - Database restore: `pg_restore`
- Monitoring recommendations
- Scaling considerations

**Deliverable:** Production-ready containerized system with deployment documentation

---

## Total Estimated Time: 18-24 hours

## Implementation Order
**Sequential phases, each fully tested before proceeding:**
1. Phase 1: Database Foundation
2. Phase 2: Classification Agents
3. Phase 3: Multi-Agent Orchestrator
4. Phase 4: FastAPI REST API
5. Phase 5: API Key Authentication
6. Phase 6: Docker & Deployment

## Agile Workflow Benefits
- ✅ Each phase is independently deployable and demonstrable
- ✅ Testing integrated throughout (catch issues early)
- ✅ Documentation stays current with code
- ✅ Can demo progress to stakeholders after each phase
- ✅ Can pivot or adjust based on learnings
- ✅ Reduced risk of big-bang integration issues

## After Each Phase Checklist
- [ ] All tests passing (unit + integration)
- [ ] Documentation complete and reviewed
- [ ] Code committed to git with descriptive message
- [ ] Demo the new functionality
- [ ] Get feedback before proceeding to next phase

## Key Architectural Decisions
- **aiosql + asyncpg**: Explicit SQL control, high performance, async-native
- **Alembic**: Industry-standard schema migration management
- **FastAPI**: Modern async framework with automatic API documentation
- **Google ADK Multi-Agent**: Coordinated agent orchestration for complex workflows
- **API Key Authentication**: Simple, effective security suitable for backend-to-frontend communication
- **Docker**: Containerization for consistent deployment across environments

## Future Enhancements (Post-MVP)
- User authentication (OAuth2) for multi-tenant support
- WebSocket support for real-time article notifications
- Full-text search using PostgreSQL's built-in capabilities
- Article summarization using LLMs
- Sentiment analysis on articles
- Analytics dashboard
- Scheduled jobs for automatic article fetching
- Additional news sources beyond Jamaica Gleaner
