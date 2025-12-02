# JAccountable Backend

A Python backend system that monitors Jamaica Gleaner newspaper for government accountability stories using AI-powered news-gathering agents.

## What This Project Does

JAccountable Backend is an intelligent news monitoring system specifically designed to track government accountability issues in Jamaica. The system:

- **Monitors Jamaica Gleaner**: Automatically scrapes two key sections (Lead Stories and News) of Jamaica's premier newspaper
- **AI-Powered Analysis**: Uses Google's Agent Development Kit (ADK) with LLM agents to intelligently identify articles related to government accountability
- **Relevance Scoring**: Assigns relevance scores (1-10) to articles based on keywords like "corruption", "investigation", "scandal", "embezzled", etc.
- **Structured Output**: Returns organized JSON data with article URLs, titles, and relevance explanations
- **Ethical Scraping**: Implements proper crawl delays and respectful web scraping practices

The system specifically looks for articles mentioning:
- Government officials and political parties (JLP, PNP)
- Ministry names and government agencies
- Court cases involving public officials
- Investigations, corruption, and scandals
- Keywords indicating accountability issues

## Setup

### Prerequisites

- Python 3.12 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- [Docker](https://www.docker.com/) and Docker Compose (for local database)

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd jaacountable-backend
   ```

2. **Install dependencies using uv**:
   ```bash
   uv sync
   ```

   This will install all required dependencies including:
   - `google-adk>=1.8.0` - Google Agent Development Kit
   - `litellm>=1.74.3` - LLM abstraction layer
   - `requests` - HTTP library for web scraping
   - `alembic>=1.17.1` - Database migrations
   - `asyncpg>=0.30.0` - Async PostgreSQL driver
   - `aiosql>=13.4` - SQL query management

3. **Activate the virtual environment**:
   ```bash
   source .venv/bin/activate  # On macOS/Linux
   # or
   .venv\Scripts\activate     # On Windows
   ```

4. **Set up environment variables**:
   ```bash
   cp .env.example .env
   ```

   The default `.env` file is configured for local development with Docker PostgreSQL.

5. **Start the PostgreSQL database**:
   ```bash
   ./scripts/start-db.sh
   ```

   This will start a PostgreSQL 18 container using Docker Compose.

6. **Run database migrations**:
   ```bash
   ./scripts/migrate.sh
   ```

   This will create all necessary database tables.

## How to Run

### Via Web Interface (Recommended)

Launch the Google ADK web interface:

```bash
adk web
```

This will start a web interface where you can interact with the news gathering agent.

## Database Management

The project uses PostgreSQL for data persistence and Alembic for database migrations.

### Helper Scripts

All scripts are located in the `scripts/` directory:

- **`./scripts/start-db.sh`** - Start the PostgreSQL Docker container and wait for it to be healthy
- **`./scripts/migrate.sh`** - Run database migrations to the latest version
- **`./scripts/create-migration.sh "message"`** - Create a new migration file with manual SQL DDL

### Common Database Commands

**Start the database:**
```bash
./scripts/start-db.sh
```

**Run migrations:**
```bash
./scripts/migrate.sh
```

**Create a new migration:**
```bash
./scripts/create-migration.sh "add classifications table"
# Then edit the migration file in alembic/versions/
```

**Connect to database directly:**
```bash
docker exec -it postgres psql -U user -d jaacountable_db
```

**View database logs:**
```bash
docker-compose logs postgres
```

**Stop the database:**
```bash
docker-compose down
```

**Stop and remove all data (DESTRUCTIVE):**
```bash
docker-compose down -v
```

### Database Schema

The current schema includes:

- **`articles`** - Stores scraped news articles
  - `id` (SERIAL PRIMARY KEY)
  - `url` (VARCHAR UNIQUE NOT NULL) - Article URL for deduplication
  - `title` (VARCHAR NOT NULL)
  - `section` (VARCHAR NOT NULL) - e.g., "lead-stories", "news"
  - `published_date` (TIMESTAMPTZ)
  - `fetched_at` (TIMESTAMPTZ NOT NULL DEFAULT NOW())
  - `full_text` (TEXT) - Full article content for classification
  - Indexes on `url` and `published_date`

## Project Architecture

```
jaacountable-backend/
├── main.py                           # Entry point
├── gleaner_researcher_agent/         # Core agent system
│   ├── __init__.py                   # Module initialization
│   ├── agent.py                      # Main LLM agent definition
│   ├── tools.py                      # Web scraping tools
│   └── v1.evalset.json              # Evaluation dataset
├── alembic/                          # Database migrations
│   ├── versions/                     # Migration files
│   ├── env.py                        # Alembic environment config
│   └── script.py.mako               # Migration template
├── config/                           # Configuration modules
│   └── database.py                   # Database connection pool
├── scripts/                          # Helper scripts
│   ├── start-db.sh                   # Start PostgreSQL container
│   ├── migrate.sh                    # Run migrations
│   └── create-migration.sh          # Create new migration
├── alembic.ini                       # Alembic configuration
├── docker-compose.yml                # Docker services definition
├── .env.example                      # Environment variables template
├── pyproject.toml                    # Project configuration
├── uv.lock                          # Dependency lock file
└── README.md                        # This file
```

### Key Components

**Agent System:**
- **`agent.py`**: Defines the `news_gatherer_agent` that orchestrates the news collection process
- **`tools.py`**: Contains web scraping functions for Jamaica Gleaner sections with built-in rate limiting
- **`v1.evalset.json`**: Evaluation dataset for testing and improving agent performance

**Database Layer:**
- **`config/database.py`**: asyncpg connection pool manager for PostgreSQL
- **`alembic/`**: Database migration system using Alembic with manual SQL DDL
- **`scripts/`**: Helper scripts for database operations and deployment

## Usage Example

When running the agent, it will:

1. Scan Jamaica Gleaner's Lead Stories section
2. Scan Jamaica Gleaner's News section
3. Analyze articles for government accountability relevance
4. Return structured JSON output like:

```json
[
  {
    "url": "https://jamaica-gleaner.com/article/...",
    "title": "Minister Under Investigation for...",
    "section": "lead-stories",
    "relevance_score": 9,
    "reason": "Contains keywords 'investigation' and mentions government minister"
  }
]
```

## Development

The project uses:
- **Google ADK**: For LLM agent framework
- **LiteLLM**: Configured to use the `o4-mini` model
- **PostgreSQL 18**: Database for storing articles and classifications
- **Alembic**: Database migration management with manual SQL DDL
- **asyncpg**: Async PostgreSQL driver for high-performance database operations
- **aiosql**: SQL query management with raw SQL in `.sql` files
- **Docker**: Containerized PostgreSQL for local development
- **Ethical Web Scraping**: 10-second delays between requests to respect the target website
- **Testcontainers**: Isolated PostgreSQL containers for integration testing

### Running Tests

The project uses pytest with testcontainers for isolated database testing. Each test session spins up a fresh PostgreSQL container and runs migrations automatically.

**Run all tests:**
```bash
uv run pytest tests/
```

**Run tests with verbose output:**
```bash
uv run pytest tests/ -v
```

**Run tests with logging (shows database connection details):**
```bash
uv run pytest tests/ -v --log-cli-level=INFO
```

**Run a specific test class:**
```bash
uv run pytest tests/db/repositories/test_article_repository.py::TestInsertArticleHappyPath -v
```

**Test Features:**
- Automatic PostgreSQL container lifecycle management
- Alembic migrations run automatically on test database
- Transaction rollback after each test for isolation
- BDD-style test format (Given/When/Then comments)
- Tests organized into classes by category (HappyPath, ValidationErrors, DatabaseConstraints, EdgeCases)
- pytest-xdist available for parallel test execution across multiple test files

**Parallel Test Execution:**

The project includes pytest-xdist for running tests in parallel. Due to session-scoped async database fixtures, parallel execution works best across different test files:

```bash
# Run test files in parallel (each file runs in its own worker)
uv run pytest tests/ -n auto --dist loadfile
```

Note: Tests within a single file that use database fixtures run sequentially to maintain event loop compatibility.

### Database Development Workflow

1. **Create a new migration:**
   ```bash
   ./scripts/create-migration.sh "description of changes"
   ```

2. **Edit the migration file** in `alembic/versions/`:
   ```python
   def upgrade() -> None:
       """Upgrade schema."""
       op.execute("""
           CREATE TABLE your_table (
               id SERIAL PRIMARY KEY,
               ...
           )
       """)

   def downgrade() -> None:
       """Downgrade schema."""
       op.execute("DROP TABLE IF EXISTS your_table")
   ```

3. **Test the migration:**
   ```bash
   ./scripts/migrate.sh
   ```

4. **Verify in database:**
   ```bash
   docker exec -it postgres psql -U user -d jaacountable_db -c "\dt"
   ```

### Adding New Classifiers

The system supports multiple AI classifiers for different accountability topics. Each classifier analyzes articles and determines relevance to its specific topic.

**Current Classifiers:**
- `CORRUPTION` - Detects corruption, contract irregularities, OCG investigations
- `HURRICANE_RELIEF` - Tracks disaster relief fund allocation and management

#### How to Add a New Classifier

**Step 1: Add the Classifier Type**

Edit `src/services/article_classification/models.py` and add your new classifier to the `ClassifierType` enum:

```python
class ClassifierType(str, Enum):
    """Types of classifiers available for article analysis."""
    CORRUPTION = "CORRUPTION"
    HURRICANE_RELIEF = "HURRICANE_RELIEF"
    EDUCATION_SPENDING = "EDUCATION_SPENDING"  # NEW CLASSIFIER
```

**Step 2: Write Tests for the New Classifier**

Add tests to `tests/services/article_classification/test_models.py`:

```python
async def test_classifier_type_education_spending_succeeds(self):
    # Given: a ClassificationResult with EDUCATION_SPENDING classifier_type
    # When: creation is attempted
    # Then: ClassificationResult is created successfully
    result = ClassificationResult(
        is_relevant=True,
        confidence=0.90,
        reasoning="Article discusses education budget allocation",
        classifier_type=ClassifierType.EDUCATION_SPENDING,
        model_name="gpt-4o-mini",
    )
    assert result.classifier_type == ClassifierType.EDUCATION_SPENDING
```

**Step 3: Implement the Classifier Agent**

Create a new classifier agent that uses the `ClassificationInput` and returns `ClassificationResult`:

```python
from src.services.article_classification.models import (
    ClassificationInput,
    ClassificationResult,
    ClassifierType,
)

async def classify_education_spending(input_data: ClassificationInput) -> ClassificationResult:
    """
    Classify article relevance to education spending accountability.

    Args:
        input_data: Article content and metadata

    Returns:
        Classification result with relevance decision and reasoning
    """
    # Your LLM agent implementation here
    # Analyze input_data.full_text, input_data.title, etc.

    return ClassificationResult(
        is_relevant=True,
        confidence=0.85,
        reasoning="Article discusses education ministry budget allocation",
        key_entities=["Ministry of Education", "Budget Allocation"],
        classifier_type=ClassifierType.EDUCATION_SPENDING,
        model_name="gpt-4o-mini",
    )
```

**Step 4: Update Database Schema (if needed)**

If you need to store classifier-specific metadata, create a new migration:

```bash
./scripts/create-migration.sh "add education_spending classifier support"
```

**Step 5: Run Tests**

```bash
# Run classification model tests
uv run pytest tests/services/article_classification/test_models.py -v

# Run your new classifier tests
uv run pytest tests/services/article_classification/test_education_spending_classifier.py -v
```

#### Classification Workflow

The classification system follows this workflow:

1. **Extract** - Article content is extracted from news source
   - Returns: `ExtractedArticleContent` (from `src/services/article_extractor/models.py`)

2. **Prepare Input** - Create `ClassificationInput` from extracted content
   ```python
   classification_input = ClassificationInput(
       url=url,
       title=extracted.title,
       section=section,  # From scraper context
       full_text=extracted.full_text,
       published_date=extracted.published_date,
   )
   ```

3. **Classify** - Pass to classifier agent
   ```python
   result = await corruption_classifier.classify(classification_input)
   ```

4. **Store** - If relevant, store article and classification in database
   ```python
   if result.is_relevant:
       # Store article (article_id generated here)
       # Store classification with result.confidence, result.reasoning, etc.
   ```

#### Classification Models

**`ClassificationInput`** - Input to classifier agents:
- `url` (str) - Article URL
- `title` (str) - Article title
- `section` (str) - News section (e.g., "Lead Stories")
- `full_text` (str) - Complete article text
- `published_date` (datetime | None) - Publication timestamp

**`ClassificationResult`** - Output from classifier agents:
- `is_relevant` (bool) - Relevance decision
- `confidence` (float) - Confidence score (0.0 to 1.0)
- `reasoning` (str) - Explanation for decision
- `key_entities` (list[str]) - Extracted entities
- `classifier_type` (ClassifierType) - Which classifier produced this result
- `model_name` (str) - LLM model used (e.g., "gpt-4o-mini")

**`ClassifierType`** - Enum of available classifiers:
- `CORRUPTION`
- `HURRICANE_RELIEF`
- Add your own as needed

## Contributing

When contributing to this project, please ensure:
- Maintain the 10-second crawl delay in scraping functions
- Follow the existing agent prompt structure
- Add new evaluation cases to the evalset when adding features
- Keep the focus on government accountability topics
- Write database migrations using manual SQL DDL (not SQLAlchemy ORM)
- Test migrations locally before committing
- Include both `upgrade()` and `downgrade()` functions in all migrations
- Use raw SQL with aiosql for database queries (stored in `.sql` files)