# Article Case Association Analysis

## Current State

### Existing Schema
- **articles** table: Stores article content with URL deduplication
- **classifications** table: 1:N relationship with articles (one article can have multiple classifications)
- **news_sources** table: Tracks source publications

### Key Observation
The `ClassificationResult.key_entities` field is already extracted by classifiers but **NOT currently stored** in the database (see `src/article_classification/models.py:168` and comment at line 146).

Example entities from user:
- Ruel Reid (Person)
- Fritz Pinnock (Person)
- Sharen Reid (Person)
- Sharelle Reid (Person)
- Financial Investigations Division (Organization)

---

## Assumptions

### 1. Case Definition
A "case" represents a specific corruption scandal, investigation, or accountability incident that may span multiple articles over time. Examples:
- "Education Ministry Corruption Investigation" (involving Ruel Reid, Fritz Pinnock, etc.)
- "Hurricane Relief Fund Mismanagement 2024"
- "Port Authority Contract Irregularities"

### 2. Entity Normalization Challenge
The same entity may appear with different names:
- "Ruel Reid" vs "Mr. Reid" vs "Education Minister Reid"
- Need entity resolution strategy (exact match, fuzzy match, or AI-based normalization)

### 3. Association Criteria
Articles belong to the same case when they share:
- **High entity overlap** (e.g., 3+ shared key entities)
- **Same investigation/incident** (determined by AI or human curation)
- **Temporal proximity** (published within reasonable timeframe)

### 4. Storage Strategy
Store entities only for **relevant articles** (articles that passed classification threshold), since irrelevant articles are filtered out anyway.

### 5. Entity Extraction Source
Leverage existing `ClassificationResult.key_entities` from AI classifiers rather than building separate NER system.

### 6. Human-in-the-Loop
AI suggests case associations, but humans may need to review/refine groupings for accuracy.

---

## Approach 1: Entity-Based Association (Implicit Cases)

### Concept
Store entities in a separate table with many-to-many relationships to articles. "Cases" are discovered dynamically by querying articles that share entities.

### Schema Changes

```sql
-- New table: entities (SIMPLIFIED - no entity_type field per user preference)
CREATE TABLE entities (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,  -- Display name (e.g., "Ruel Reid")
    normalized_name TEXT NOT NULL,  -- AI-normalized canonical name
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_entities_normalized_name ON entities(normalized_name);
CREATE INDEX idx_entities_name ON entities(name);

-- New junction table: article_entities
CREATE TABLE article_entities (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    classifier_type TEXT NOT NULL,  -- Which classifier extracted this (CORRUPTION, etc.)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(article_id, entity_id)
);
CREATE INDEX idx_article_entities_article ON article_entities(article_id);
CREATE INDEX idx_article_entities_entity ON article_entities(entity_id);
```

### Pydantic Models

```python
# In src/article_persistence/models/domain.py

class Entity(BaseModel):
    """
    Represents a named entity extracted from articles.

    The normalized_name field stores an AI-generated canonical form
    to handle entity name variations (e.g., "Ruel Reid", "Mr. Reid",
    "Education Minister Reid" all map to same normalized_name).
    """
    id: int | None = None
    name: str  # Display name (as extracted from article)
    normalized_name: str  # AI-normalized canonical name for deduplication
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(from_attributes=True)

    @field_validator('name', 'normalized_name')
    @classmethod
    def validate_required_string(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Field cannot be empty')
        return v.strip()


class ArticleEntity(BaseModel):
    """Links articles to entities (many-to-many relationship)."""
    id: int | None = None
    article_id: int
    entity_id: int
    classifier_type: str  # Which classifier extracted this entity
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(from_attributes=True)

    @field_validator('classifier_type')
    @classmethod
    def validate_classifier_type(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Classifier type cannot be empty')
        return v.strip()
```

### Query Example: Find Related Articles

```sql
-- Find articles that share 2+ entities with article 123
SELECT
    a.id,
    a.title,
    a.url,
    a.published_date,
    COUNT(DISTINCT ae2.entity_id) as shared_entity_count,
    ARRAY_AGG(DISTINCT e.name) as shared_entities
FROM articles a
JOIN article_entities ae2 ON a.id = ae2.article_id
JOIN entities e ON ae2.entity_id = e.id
WHERE ae2.entity_id IN (
    SELECT entity_id FROM article_entities WHERE article_id = 123
)
AND a.id != 123
GROUP BY a.id, a.title, a.url, a.published_date
HAVING COUNT(DISTINCT ae2.entity_id) >= 2
ORDER BY shared_entity_count DESC;
```

### Pros
- **Flexible discovery**: No need to pre-define cases
- **Entity-centric queries**: "Show all articles mentioning Ruel Reid"
- **Automatic clustering**: Articles naturally group by shared entities
- **Low maintenance**: No manual case curation required

### Cons
- **No explicit case names**: "Ruel Reid corruption case" is just a query result, not a named entity
- **Threshold ambiguity**: How many shared entities = same case? 2? 3? 5?
- **Entity quality dependent**: Poor entity extraction → poor associations
- **Entity name variations**: "Ministry of Education" vs "Education Ministry" vs "MoE"

---

## Approach 2: Explicit Case Entity (Manual/AI Curation)

### Concept
Create a `cases` table where cases are explicitly defined with names and descriptions. Articles are associated with cases through a junction table.

### Schema Changes

```sql
-- New table: cases
CREATE TABLE cases (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,  -- "Education Ministry Corruption Investigation"
    description TEXT,  -- Optional summary of the case
    case_type TEXT,  -- CORRUPTION, HURRICANE_RELIEF, etc. (mirrors ClassifierType)
    status TEXT DEFAULT 'ACTIVE',  -- ACTIVE, RESOLVED, ARCHIVED
    primary_entities TEXT[],  -- Key people/orgs (e.g., ['Ruel Reid', 'Fritz Pinnock'])
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_cases_case_type ON cases(case_type);
CREATE INDEX idx_cases_status ON cases(status);

-- New junction table: article_cases
CREATE TABLE article_cases (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    association_confidence FLOAT,  -- AI confidence (0.0-1.0) that article belongs to case
    associated_by TEXT,  -- 'AI', 'MANUAL', or user ID
    associated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(article_id, case_id)
);
CREATE INDEX idx_article_cases_article ON article_cases(article_id);
CREATE INDEX idx_article_cases_case ON article_cases(case_id);
```

### Pydantic Models

```python
# In src/article_persistence/models/domain.py

class Case(BaseModel):
    """Represents a corruption case or accountability incident."""
    id: int | None = None
    name: str
    description: str | None = None
    case_type: str | None = None  # CORRUPTION, HURRICANE_RELIEF, etc.
    status: str = "ACTIVE"
    primary_entities: list[str] = []  # Key people/organizations
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(from_attributes=True)

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Case name cannot be empty')
        return v.strip()

    @field_validator('status')
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = ['ACTIVE', 'RESOLVED', 'ARCHIVED']
        if v not in allowed:
            raise ValueError(f'Status must be one of {allowed}')
        return v


class ArticleCase(BaseModel):
    """Links articles to cases with association metadata."""
    id: int | None = None
    article_id: int
    case_id: int
    association_confidence: float | None = None
    associated_by: str | None = None  # 'AI', 'MANUAL', or user ID
    associated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(from_attributes=True)

    @field_validator('association_confidence')
    @classmethod
    def validate_confidence(cls, v: float | None) -> float | None:
        if v is not None and (v < 0.0 or v > 1.0):
            raise ValueError('Confidence must be between 0.0 and 1.0')
        return v
```

### Query Example: Get All Articles in a Case

```sql
-- Get all articles associated with "Education Ministry Corruption" case
SELECT
    a.*,
    ac.association_confidence,
    ac.associated_by
FROM articles a
JOIN article_cases ac ON a.id = ac.article_id
JOIN cases c ON ac.case_id = c.id
WHERE c.name = 'Education Ministry Corruption Investigation'
ORDER BY a.published_date DESC;
```

### Workflow: AI-Suggested Case Association

1. **New article classified** → Extracts key entities
2. **AI checks existing cases** → Compares article entities with `cases.primary_entities`
3. **Suggests case association** → If high overlap, insert into `article_cases` with `associated_by='AI'`
4. **Human review** (optional) → Approve/reject/modify AI suggestions

### Pros
- **Human-readable case names**: "Education Ministry Corruption" vs query for "articles sharing Ruel Reid"
- **Explicit metadata**: Track case status, timeline, primary entities
- **Clear boundaries**: Article either belongs to case or doesn't
- **UI-friendly**: Easy to display "Case Dashboard" showing all related articles

### Cons
- **Requires case creation**: Who creates cases? When?
- **Manual curation overhead**: Need UI and workflow for case management
- **Missed associations**: New articles might not match existing case patterns
- **Rigid structure**: Hard to represent articles spanning multiple cases

---

## Approach 3: Hybrid (Entity Storage + Case Curation)

### Concept
Combine Approach 1 and 2: Store entities for flexible querying, AND create explicit cases for curated groupings. Best of both worlds.

### Schema Changes
All tables from Approach 1 AND Approach 2:
- `entities` + `article_entities` (for entity-based queries)
- `cases` + `article_cases` (for curated case groupings)

### Workflow

1. **Article classified** → Extract entities → Store in `entities` + `article_entities`
2. **AI case suggestion** → Query articles with high entity overlap → Suggest case grouping
3. **Human creates case** → Name it "Education Ministry Corruption" → Associate articles
4. **Both query modes available**:
   - Entity-based: "All articles mentioning Ruel Reid"
   - Case-based: "All articles in Education Ministry Corruption case"

### Pros
- **Maximum flexibility**: Entity queries + case queries
- **AI-assisted curation**: Entities help suggest case groupings
- **Gradual workflow**: Start with entities, curate cases over time
- **Redundancy protection**: Entities provide fallback if case associations lag

### Cons
- **Most complex**: Highest implementation cost
- **Schema complexity**: 4 new tables instead of 2
- **Maintenance overhead**: Keep entities and cases synchronized
- **Storage cost**: Storing both entities and case associations

---

## Selected Approach: Entity-Based with AI Resolution

Based on user preferences:
- ✅ **Approach 1**: Entity-based association (implicit cases through entity overlap)
- ✅ **AI entity resolution**: Use LLM to normalize entity name variations
- ✅ **No entity type categorization**: Simple schema with just entity names

### Rationale
1. **Leverage existing work**: `ClassificationResult.key_entities` already extracted, just need to store them
2. **Low overhead**: No manual case curation required
3. **Validate hypothesis**: Test if entity-based clustering groups articles well
4. **Incremental**: Can add explicit `cases` table later if clustering proves insufficient
5. **High accuracy**: AI resolution catches name variations that exact matching would miss

---

## Implementation Plan

### Phase 1: Database Schema & Models

**Step 1.1: Create Migration for Entities Tables**
- File: `alembic/versions/YYYY_MM_DD_HHMM-<hash>_add_entities_tables.py`
- Create `entities` table with `name` and `normalized_name` fields
- Create `article_entities` junction table
- Add indexes for performance

**Step 1.2: Add Pydantic Domain Models**
- File: `src/article_persistence/models/domain.py`
- Add `Entity` model (no entity_type field)
- Add `ArticleEntity` model
- Add field validators

**Step 1.3: Run Migration**
- Execute: `./scripts/migrate.sh`
- Verify tables created successfully

### Phase 2: AI Entity Resolution Service

**Step 2.1: Create Entity Normalization Service**
- File: `src/services/entity_resolution/entity_normalizer.py`
- Implement LLM-based entity resolution:
  - Input: Raw entity name (e.g., "Mr. Reid")
  - Output: Normalized canonical name (e.g., "ruel reid")
  - Use lightweight model (gpt-4o-mini or similar)
  - Prompt engineering: "Normalize this entity name to canonical form"
  - Handle edge cases: acronyms (OCG), titles (Mr., Dr.), organizations

**Step 2.2: Create Entity Matching Service**
- File: `src/services/entity_resolution/entity_matcher.py`
- Implement logic to find or create entities:
  1. Normalize incoming entity name using AI
  2. Check if `normalized_name` exists in `entities` table
  3. If exists: return existing `entity_id`
  4. If not: insert new entity with both `name` and `normalized_name`
- Batch processing for efficiency (normalize multiple entities in one LLM call)

**Step 2.3: Add Configuration**
- File: `.env` (example)
- Add settings for entity resolution:
  - `ENTITY_RESOLUTION_MODEL=gpt-4o-mini`
  - `ENTITY_RESOLUTION_ENABLED=true` (feature flag)
  - `ENTITY_BATCH_SIZE=10` (normalize N entities per API call)

### Phase 3: Repository Layer

**Step 3.1: Create Entity Repository**
- File: `src/article_persistence/repositories/entity_repository.py`
- Implement methods:
  - `find_by_normalized_name(normalized_name: str) -> Entity | None`
  - `insert_entity(name: str, normalized_name: str) -> Entity`
  - `find_entities_by_article_id(article_id: int) -> list[Entity]`
  - `find_articles_by_entity_id(entity_id: int) -> list[int]`

**Step 3.2: Create Article-Entity Repository**
- File: `src/article_persistence/repositories/article_entity_repository.py`
- Implement methods:
  - `link_article_to_entity(article_id: int, entity_id: int, classifier_type: str) -> ArticleEntity`
  - `find_related_articles(article_id: int, min_shared_entities: int = 2) -> list[dict]`
    - Returns articles sharing N+ entities with given article
    - Include shared entity count and entity names

### Phase 4: Update Classification Storage Workflow

**Step 4.1: Update Article Storage Service**
- File: `src/article_persistence/services/article_storage_service.py` (or equivalent)
- Modify storage workflow to:
  1. Store article as currently done
  2. Store classification as currently done
  3. **NEW**: Extract `key_entities` from `ClassificationResult`
  4. **NEW**: For each entity:
     - Normalize using AI entity resolution service
     - Find or create entity in `entities` table
     - Link to article in `article_entities` table

**Step 4.2: Handle Batch Processing**
- Optimize: normalize all entities from a classification in single LLM call
- Error handling: if normalization fails, fallback to exact match or skip entity
- Logging: track entity resolution success rate

### Phase 5: Query Utilities & API

**Step 5.1: Create Entity Query Service**
- File: `src/services/entity_association/entity_query_service.py`
- Implement high-level query methods:
  - `find_related_articles(article_id: int, threshold: int = 2) -> list[dict]`
    - Returns articles sharing threshold+ entities
    - Includes: article metadata, shared entity count, entity names
  - `find_articles_by_entity(entity_name: str) -> list[dict]`
    - Normalize entity name using AI
    - Find all articles mentioning that entity
  - `get_entity_timeline(entity_name: str) -> list[dict]`
    - Articles mentioning entity, sorted by published_date
    - Useful for tracking how a case unfolds over time

**Step 5.2: Add API Endpoints** (if API layer exists)
- `GET /articles/{article_id}/related` - Get related articles by entity overlap
- `GET /entities/{entity_name}/articles` - Get all articles mentioning entity
- `GET /entities/{entity_name}/timeline` - Get chronological article timeline

### Phase 6: Testing

**Step 6.1: Unit Tests for Entity Resolution**
- File: `tests/services/entity_resolution/test_entity_normalizer.py`
- Test cases:
  - "Ruel Reid" → "ruel reid"
  - "Mr. Reid" → "ruel reid"
  - "Education Minister Reid" → "ruel reid"
  - "OCG" → "ocg" (acronym handling)
  - "Ministry of Education" → "ministry of education"
- Mark as `@pytest.mark.integration` (makes LLM API calls)

**Step 6.2: Unit Tests for Entity Repositories**
- File: `tests/article_persistence/repositories/test_entity_repository.py`
- Test CRUD operations with test database

**Step 6.3: Integration Tests for Storage Workflow**
- File: `tests/article_persistence/services/test_article_storage_with_entities.py`
- Test full workflow:
  1. Store article with classification containing key_entities
  2. Verify entities created/linked
  3. Query related articles
  4. Verify entity deduplication (same entity mentioned in multiple articles)

**Step 6.4: Test Related Article Queries**
- File: `tests/services/entity_association/test_entity_query_service.py`
- Test scenarios:
  - Articles with 3+ shared entities → should be related
  - Articles with 0-1 shared entities → should not be related
  - Entity name variation handling

### Phase 7: Monitoring & Optimization

**Step 7.1: Add Metrics**
- Track entity resolution API calls/cost
- Track entity deduplication rate (how many variations map to same entity)
- Track related article query performance

**Step 7.2: Consider Caching**
- Cache entity normalization results (e.g., "Mr. Reid" → "ruel reid")
- Reduces redundant LLM calls for common entity variations
- Use simple dict cache or Redis

---

## AI Entity Resolution Prompt Strategy

### Normalization Prompt Template

```python
"""
You are an entity normalization system. Given an entity name extracted from a news article,
return the canonical normalized form for deduplication purposes.

Rules:
1. Convert to lowercase
2. Remove titles (Mr., Mrs., Dr., Minister, etc.)
3. Keep full names for people (e.g., "ruel reid" not just "reid")
4. Keep full organization names (e.g., "office of contractor general")
5. Preserve acronyms as-is (e.g., "OCG" → "ocg")
6. Remove extra whitespace

Examples:
- "Ruel Reid" → "ruel reid"
- "Mr. Reid" → "ruel reid"
- "Education Minister Ruel Reid" → "ruel reid"
- "Office of the Contractor General" → "office of contractor general"
- "OCG" → "ocg"
- "Ministry of Education" → "ministry of education"

Entity to normalize: "{entity_name}"

Return ONLY the normalized form, nothing else.
"""
```

### Batch Processing Prompt

```python
"""
Normalize the following entity names to their canonical forms. Return JSON array.

Entities:
{entities_json}

Return format:
[
  {"original": "Mr. Reid", "normalized": "ruel reid"},
  {"original": "OCG", "normalized": "ocg"}
]
"""
```

---

## Critical Files

### To Be Created
- `alembic/versions/YYYY_MM_DD_HHMM-<hash>_add_entities_tables.py` - Migration
- `src/services/entity_resolution/entity_normalizer.py` - AI normalization service
- `src/services/entity_resolution/entity_matcher.py` - Entity matching logic
- `src/article_persistence/repositories/entity_repository.py` - Entity CRUD
- `src/article_persistence/repositories/article_entity_repository.py` - Junction table CRUD
- `src/services/entity_association/entity_query_service.py` - High-level query utilities
- `tests/services/entity_resolution/test_entity_normalizer.py` - Normalization tests
- `tests/article_persistence/repositories/test_entity_repository.py` - Repository tests
- `tests/services/entity_association/test_entity_query_service.py` - Query tests

### To Be Modified
- `src/article_persistence/models/domain.py` - Add `Entity` and `ArticleEntity` models
- `src/article_persistence/services/article_storage_service.py` - Update to persist entities
- `.env.example` - Add entity resolution configuration

---

## Summary

This plan implements **entity-based article association** with **AI-powered entity normalization** to handle name variations. The system will:

1. **Extract entities** from classification results (already done by classifiers)
2. **Normalize entities** using LLM to create canonical forms ("Mr. Reid" → "ruel reid")
3. **Store entities** in database with deduplication
4. **Link articles to entities** via many-to-many relationship
5. **Query related articles** by finding articles that share 2+ entities

This approach enables discovering corruption "cases" organically without manual curation, while the AI normalization ensures robust entity matching across name variations.

Future enhancement: Add explicit `cases` table if entity-based clustering proves insufficient for grouping articles.
