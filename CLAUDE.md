# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python backend project called "jaacountable-backend" that implements a news-gathering system focused on Jamaica Gleaner newspaper. The project uses Google ADK (Agent Development Kit) to create LLM agents that scrape and analyze news articles for government accountability topics.

## Key Architecture

### Core Components

- **Main Entry Point**: `main.py` - Simple entry point with basic "Hello World" functionality
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
./scripts/start-db.sh

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

The project uses pytest with testcontainers for isolated database testing.

**Run tests:**
```bash
# Run all tests
uv run pytest tests/

# Run with verbose output
uv run pytest tests/ -v

# Run with logging (shows database connection details)
uv run pytest tests/ -v --log-cli-level=INFO
```

**Test Infrastructure:**
- `tests/conftest.py` - Pytest fixtures for database testing
- `testcontainers` - Spins up isolated PostgreSQL containers per test session
- Automatic Alembic migrations on test database
- Transaction rollback after each test for isolation
- BDD-style test format (Given/When/Then comments)

**Available Fixtures:**
- `postgres_container` - Session-scoped PostgreSQL container
- `test_database_url` - Connection URL from container
- `run_migrations` - Runs Alembic migrations on test database
- `db_pool` - asyncpg connection pool
- `db_connection` - Connection with automatic transaction rollback

The project also includes an evaluation set (`v1.evalset.json`) for testing agent performance.

## Important Implementation Details

### Database Architecture
- **Raw SQL Approach**: Uses manual SQL DDL in Alembic migrations, NOT SQLAlchemy ORM models
- **Async Operations**: All database operations use asyncpg for async/await patterns
- **Connection Pooling**: `config/database.py` manages connection pools with proper lifecycle
- **Query Management**: Future queries will use aiosql with SQL stored in `.sql` files
- **Migration Strategy**: All migrations include both `upgrade()` and `downgrade()` functions
- **Environment Config**: Database URL loaded from `.env` file, managed by Alembic

**Current Schema:**
- `articles` table: Stores scraped articles with deduplication via unique URL constraint
  - Indexes on `url` and `published_date` for performance
  - `fetched_at` tracks when article was scraped
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