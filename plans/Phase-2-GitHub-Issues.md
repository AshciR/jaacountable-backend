# Phase 2: Classification Agents - GitHub Issues

This document contains 9 GitHub issues for implementing Phase 2 of the High-Level Plan.

**Development Approach:** Sequential (complete corruption classifier fully before starting hurricane relief)

**Total Estimated Time:** 14.5-17 hours (includes article extraction utility)

---

## Issue #0: Create article extraction utility (FOUNDATION)

**Labels:** `enhancement`, `phase-2`, `foundation`, `critical`
**Priority:** Critical (blocking all other issues)
**Estimated Effort:** 1-2 hours

### Description

Create a utility service to extract full article text from news article URLs. This is required to populate the `full_text` field in the `ClassificationInput` schema.

**Proof of Concept:** ✅ Validated extraction feasibility with WebFetch test

**Implementation Approach:** ✅ BeautifulSoup with **Strategy Pattern**

### Design Pattern: Strategy Pattern

Different news sources have different HTML structures. Using the Strategy pattern provides:

- ✅ **Extensibility**: Add new sources by creating new extractor class
- ✅ **Maintainability**: Each source's logic is isolated
- ✅ **Testability**: Test each extractor independently with fixtures
- ✅ **Open/Closed Principle**: Open for extension, closed for modification
- ✅ **Single Responsibility**: Each extractor handles one source

### Architecture

```
src/services/article_extractor/
├── __init__.py                  # Exports ArticleExtractionService
├── base.py                      # ArticleExtractor ABC
├── gleaner_extractor.py         # GleanerExtractor strategy
├── radio_jamaica_extractor.py   # RadioJamaicaExtractor strategy
└── service.py                   # ArticleExtractionService (context)
```

### Tasks

- [ ] Create `src/services/article_extractor/` module directory
- [ ] Create `src/services/article_extractor/base.py`:
  - Define `ArticleExtractor(ABC)` abstract base class
  - Abstract method: `extract(html: str, url: str) -> ArticleContent`
- [ ] Create `src/services/article_extractor/gleaner_extractor.py`:
  - Implement `GleanerExtractor(ArticleExtractor)`
  - Jamaica Gleaner-specific HTML parsing
  - Selectors for title, author, date, article body
- [ ] Create `src/services/article_extractor/radio_jamaica_extractor.py`:
  - Implement `RadioJamaicaExtractor(ArticleExtractor)`
  - Radio Jamaica News-specific HTML parsing
  - Selectors for title, author, date, article body
- [ ] Create `src/services/article_extractor/service.py`:
  - Implement `ArticleExtractionService` class
  - Domain-to-extractor mapping dictionary
  - `extract_article_content(url: str) -> ArticleContent` public method
  - Fetches HTML with requests
  - Selects strategy based on URL domain
  - Executes extraction and returns ArticleContent
- [ ] Create `src/services/article_extractor/__init__.py`:
  - Export `ArticleExtractionService` as public API
- [ ] Define `ArticleContent` Pydantic model in `src/schemas/article.py`:
  - `title: str`
  - `full_text: str`
  - `author: str | None`
  - `published_date: datetime | None`
- [ ] Add error handling:
  - Network failures (requests.HTTPError)
  - Invalid URLs
  - Unsupported domains (ValueError)
  - Parsing failures (graceful fallbacks)
- [ ] Write unit tests in `tests/services/article_extractor/`:
  - `test_base.py` - Test abstract base
  - `test_gleaner_extractor.py` - Test Gleaner strategy with HTML fixtures
  - `test_radio_jamaica_extractor.py` - Test Radio Jamaica strategy with fixtures
  - `test_service.py` - Test service with mocked requests
  - Test error cases (unsupported domain, network failure)

### Implementation (Strategy Pattern)

**Base Strategy:**
```python
# src/services/article_extractor/base.py
from abc import ABC, abstractmethod
from src.schemas.article import ArticleContent

class ArticleExtractor(ABC):
    """Base strategy for extracting article content from HTML."""

    @abstractmethod
    def extract(self, html: str, url: str) -> ArticleContent:
        """Extract article content from HTML.

        Args:
            html: Raw HTML content
            url: Article URL (for context)

        Returns:
            Extracted and structured article content
        """
        pass
```

**Concrete Strategy Example:**
```python
# src/services/article_extractor/gleaner_extractor.py
from bs4 import BeautifulSoup
from .base import ArticleExtractor
from src.schemas.article import ArticleContent

class GleanerExtractor(ArticleExtractor):
    """Extraction strategy for Jamaica Gleaner articles."""

    def extract(self, html: str, url: str) -> ArticleContent:
        soup = BeautifulSoup(html, 'html.parser')

        # Gleaner-specific selectors
        title = soup.find('h1', class_='article-title').get_text(strip=True)
        author_elem = soup.find('span', class_='author-name')
        author = author_elem.get_text(strip=True) if author_elem else None

        # Extract article body paragraphs
        article_body = soup.find('div', class_='article-body')
        paragraphs = article_body.find_all('p')
        full_text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs)

        return ArticleContent(
            title=title,
            full_text=full_text,
            author=author,
            published_date=self._parse_date(soup)
        )

    def _parse_date(self, soup):
        # Gleaner-specific date parsing
        ...
```

**Service (Context):**
```python
# src/services/article_extractor/classification_service.py
import requests
from urllib.parse import urlparse
from .gleaner_extractor import GleanerExtractor
from .radio_jamaica_extractor import RadioJamaicaExtractor

class ArticleExtractionService:
    """Main service for extracting article content using strategies."""

    def __init__(self):
        # Map domains to extraction strategies
        self.extractors = {
            'jamaica-gleaner.com': GleanerExtractor(),
            'radiojamaicanewsonline.com': RadioJamaicaExtractor(),
        }

    def extract_article_content(self, url: str) -> ArticleContent:
        """Extract article content from URL.

        Args:
            url: Article URL

        Returns:
            Extracted article content

        Raises:
            ValueError: If domain not supported
            requests.HTTPError: If fetching fails
        """
        # Fetch HTML
        response = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; JaaccountableBot/1.0)'
        })
        response.raise_for_status()

        # Select strategy based on domain
        domain = urlparse(url).netloc.replace('www.', '')
        extractor = self.extractors.get(domain)

        if not extractor:
            raise ValueError(f"No extractor configured for domain: {domain}")

        # Execute extraction strategy
        return extractor.extract(response.text, url)
```

**Adding New Sources:**
```python
# To add Jamaica Observer support:
# 1. Create observer_extractor.py with ObserverExtractor class
# 2. Add to classification_service.py:
self.extractors['jamaicaobserver.com'] = ObserverExtractor()
# That's it! No modification to existing code needed.
```

### Example Output (from POC)

```python
ArticleContent(
    title="Ruel Reid and co. fraud trial to proceed as court rejects claim of nullity",
    full_text="Senior Parish Court Judge Sanchia Burrell has rejected another attempt...",
    author="Racquel Porter",
    published_date=datetime(2025, 11, 18, 15, 27)
)
```

### POC Test Result

Successfully extracted content from:
- URL: `https://radiojamaicanewsonline.com/local/ruel-reid-and-co-fraud-trial-to-proceed-as-court-rejects-claim-of-nullity`
- Title: ✅ Extracted
- Date: ✅ November 18, 2025
- Author: ✅ Racquel Porter
- Full text: ✅ All paragraphs, clean (no HTML/ads)

### Acceptance Criteria

- ✅ Strategy pattern implemented with base class and concrete strategies
- ✅ Can extract article content from Radio Jamaica News and Jamaica Gleaner URLs
- ✅ Returns structured data (not raw HTML)
- ✅ Handles errors gracefully (network failures, invalid URLs, unsupported domains)
- ✅ Each extractor can be tested independently with HTML fixtures
- ✅ Easy to add new sources (create new extractor class + register in service)
- ✅ Tests pass for sample articles from each source
- ✅ Works with both local and production environments

### Dependencies

None (foundation issue - must be completed first)

### Next Step

Once complete, orchestrator can call this utility to get `full_text`, then construct `ClassificationInput` for the classifier agents.

---

## Issue #1: Create shared classification output schemas

**Labels:** `enhancement`, `phase-2`, `foundation`
**Priority:** High (blocking)
**Estimated Effort:** 1 hour

### Description

Create shared Pydantic schemas for classifier agent inputs and outputs, separate from database models. These schemas will be used by both corruption and hurricane relief classifier agents.

### Tasks

- [ ] Create `src/schemas/classification.py` file
- [ ] Define `ClassifierType` enum with values:
  - `CORRUPTION`
  - `HURRICANE_RELIEF`
- [ ] Define `ClassificationInput` model (article data passed to classifiers):
  - `article_id: int`
  - `url: str`
  - `title: str`
  - `section: str`
  - `full_text: str`
  - `published_date: datetime | None`
- [ ] Define `ClassificationResult` model (agent output):
  - `is_relevant: bool`
  - `confidence: float` (0.0-1.0)
  - `reasoning: str`
  - `key_entities: List[str]` (optional, for extracted entities)
  - `classifier_type: ClassifierType`
- [ ] Add examples in docstrings for each model
- [ ] Write unit tests for schema validation in `tests/schemas/test_classification.py`

### Acceptance Criteria

- All Pydantic models validate correctly
- Confidence scores must be 0.0-1.0
- Tests cover edge cases (empty text, invalid confidence values)
- Documentation includes usage examples

### Dependencies

None (foundation issue)

---

## Issue #2: Create corruption classifier agent

**Labels:** `enhancement`, `phase-2`, `agent`, `corruption`
**Priority:** High
**Estimated Effort:** 2-3 hours

### Description

Build a specialized LLM agent that identifies corruption-related articles from Jamaica Gleaner content. The agent receives article data as structured input and returns a classification result.

### Tasks

- [ ] Create `corruption_classifier_agent/` directory at project root
- [ ] Create `corruption_classifier_agent/__init__.py` (imports agent module)
- [ ] Create `corruption_classifier_agent/agent.py`:
  - Define `corruption_classifier` using `LlmAgent`
  - Use `LiteLlm(model="o4-mini")`
  - Export as `root_agent`
  - Write detailed instruction prompt covering:
    - Role: identify corruption/accountability issues
    - Keywords: embezzlement, bribery, fraud, misuse of public funds, government misconduct, contract irregularities
    - Government agencies: OCG (Office of the Contractor General), MOCA, FID, Parliament committees
    - Expected JSON output format matching `ClassificationResult`
- [ ] Create `corruption_classifier_agent/tools.py` (placeholder if no tools needed initially)
- [ ] Ensure agent accepts article data (title, full_text, etc.) as input
- [ ] Agent outputs structured JSON matching `ClassificationResult` schema
- [ ] Default confidence threshold: 0.7 for high precision

### Example Input

```json
{
  "article_id": 123,
  "title": "OCG Investigates Ministry Contract Irregularities",
  "full_text": "The Office of the Contractor General...",
  "section": "news",
  "url": "https://jamaica-gleaner.com/article/news/...",
  "published_date": "2025-11-20T10:00:00Z"
}
```

### Example Output

```json
{
  "is_relevant": true,
  "confidence": 0.85,
  "reasoning": "Article discusses OCG investigation into contract irregularities at a government ministry, which is a corruption accountability issue.",
  "key_entities": ["OCG", "Ministry of Education"],
  "classifier_type": "CORRUPTION"
}
```

### Acceptance Criteria

- Agent can be discovered by `adk web`
- Agent processes article text and returns structured JSON
- Output matches `ClassificationResult` schema
- Prompt includes clear classification criteria for corruption/accountability
- Agent correctly identifies corruption keywords and patterns

### Dependencies

- Issue #1 (shared schemas)

---

## Issue #3: Create hurricane relief classifier agent

**Labels:** `enhancement`, `phase-2`, `agent`, `hurricane-relief`
**Priority:** High
**Estimated Effort:** 2-3 hours

### Description

Build a specialized LLM agent that identifies hurricane/disaster relief-related articles from Jamaica Gleaner content. The agent receives article data as structured input and returns a classification result.

### Tasks

- [ ] Create `hurricane_relief_classifier_agent/` directory at project root
- [ ] Create `hurricane_relief_classifier_agent/__init__.py` (imports agent module)
- [ ] Create `hurricane_relief_classifier_agent/agent.py`:
  - Define `hurricane_relief_classifier` using `LlmAgent`
  - Use `LiteLlm(model="o4-mini")`
  - Export as `root_agent`
  - Write detailed instruction prompt covering:
    - Role: identify hurricane/disaster relief issues
    - Keywords: hurricane relief, disaster funding, NEMA, ODPEM, reconstruction, relief fund allocation, emergency management
    - Disaster types: hurricanes, tropical storms, earthquakes, floods
    - Expected JSON output format matching `ClassificationResult`
- [ ] Create `hurricane_relief_classifier_agent/tools.py` (placeholder if no tools needed initially)
- [ ] Ensure agent accepts article data as input
- [ ] Agent outputs structured JSON matching `ClassificationResult` schema
- [ ] Default confidence threshold: 0.7 for high precision

### Example Input

```json
{
  "article_id": 456,
  "title": "NEMA Allocates $50M for Hurricane Relief",
  "full_text": "The National Emergency Management Agency...",
  "section": "lead-stories",
  "url": "https://jamaica-gleaner.com/article/lead/...",
  "published_date": "2025-11-15T08:30:00Z"
}
```

### Example Output

```json
{
  "is_relevant": true,
  "confidence": 0.92,
  "reasoning": "Article covers NEMA's allocation of hurricane relief funds, directly relevant to disaster relief tracking.",
  "key_entities": ["NEMA", "Hurricane Dean"],
  "classifier_type": "HURRICANE_RELIEF"
}
```

### Acceptance Criteria

- Agent can be discovered by `adk web`
- Agent processes article text and returns structured JSON
- Output matches `ClassificationResult` schema
- Prompt includes clear classification criteria for hurricane/disaster relief
- Agent correctly identifies disaster relief keywords and patterns

### Dependencies

- Issue #1 (shared schemas)

### Notes

This should be implemented AFTER Issue #2 (corruption classifier) is complete, following sequential development approach.

---

## Issue #4: Create evaluation dataset for corruption classifier

**Labels:** `testing`, `phase-2`, `corruption`
**Priority:** Medium
**Estimated Effort:** 2 hours

### Description

Create comprehensive test cases for corruption classifier using real Jamaica Gleaner article examples provided by the project owner.

### Tasks

- [ ] Collect Jamaica Gleaner articles from project owner:
  - 5-7 clear corruption/accountability cases (positive examples)
  - 3-5 non-relevant articles (sports, entertainment, general news)
  - 2-3 edge cases (mentions corruption tangentially, ambiguous)
- [ ] Create `corruption_classifier_agent/v1.evalset.json`:
  - Follow Google ADK evaluation dataset format
  - Include full article text in test cases
  - Document expected outputs (is_relevant, confidence range)
- [ ] Include test cases for:
  - Clear corruption cases (OCG investigations, bribery scandals)
  - Government financial misconduct
  - Contract irregularities
  - False positives (crime that's not corruption)
  - Ambiguous cases (mentions corruption in passing)
- [ ] Document expected behavior for each test case

### Evaluation Dataset Structure

```json
{
  "eval_set_id": "v1",
  "name": "corruption_classifier_v1",
  "description": "Evaluation dataset for corruption classifier agent",
  "eval_cases": [
    {
      "eval_id": "clear_corruption_case_1",
      "conversation": [
        {
          "user_content": {
            "parts": [{"text": "{article JSON}"}],
            "role": "user"
          },
          "final_response": {
            "parts": [{"text": "{expected ClassificationResult JSON}"}],
            "role": null
          }
        }
      ]
    }
  ]
}
```

### Acceptance Criteria

- Evaluation dataset has 10-15 diverse test cases
- Covers positive examples, negative examples, and edge cases
- Follows Google ADK `evalset.json` format
- Each case has documented expected behavior
- Uses real Jamaica Gleaner article content

### Dependencies

- Issue #2 (corruption classifier agent)
- Project owner provides article examples

---

## Issue #5: Create evaluation dataset for hurricane relief classifier

**Labels:** `testing`, `phase-2`, `hurricane-relief`
**Priority:** Medium
**Estimated Effort:** 2 hours

### Description

Create comprehensive test cases for hurricane relief classifier using real Jamaica Gleaner article examples provided by the project owner.

### Tasks

- [ ] Collect Jamaica Gleaner articles from project owner:
  - 5-7 clear disaster relief cases (NEMA, ODPEM, reconstruction)
  - 3-5 non-relevant articles (weather forecasts, sports, general news)
  - 2-3 edge cases (mentions hurricane but not relief funds)
- [ ] Create `hurricane_relief_classifier_agent/v1.evalset.json`:
  - Follow Google ADK evaluation dataset format
  - Include full article text in test cases
  - Document expected outputs
- [ ] Include test cases for:
  - Hurricane relief funding announcements
  - NEMA/ODPEM activities
  - Reconstruction efforts
  - Disaster response coordination
  - False positives (weather reports without relief funding)
  - Ambiguous cases (hurricane damage reports without relief info)
- [ ] Document expected behavior for each test case

### Evaluation Dataset Structure

Same as Issue #4, but with `eval_set_id: "v1"` and `name: "hurricane_relief_classifier_v1"`

### Acceptance Criteria

- Evaluation dataset has 10-15 diverse test cases
- Covers positive examples, negative examples, and edge cases
- Follows Google ADK `evalset.json` format
- Each case has documented expected behavior
- Uses real Jamaica Gleaner article content

### Dependencies

- Issue #3 (hurricane relief classifier agent)
- Project owner provides article examples

---

## Issue #6: Write tests for corruption classifier

**Labels:** `testing`, `phase-2`, `corruption`
**Priority:** Medium
**Estimated Effort:** 1.5 hours

### Description

Create automated tests for corruption classifier using Google ADK's AgentEvaluator.

### Tasks

- [ ] Create `corruption_classifier_agent/test_corruption_classifier.py`:
  - Use `@pytest.mark.asyncio` decorator
  - Load `.env` file for API keys
  - Use `AgentEvaluator.evaluate()` with evalset
  - Support both pytest and standalone execution
- [ ] Add docstring explaining what's being tested:
  - Correctly identifies corruption articles
  - Rejects non-relevant articles
  - Provides reasonable confidence scores (>0.7 for relevant)
  - Returns valid JSON matching schema
- [ ] Test edge cases:
  - Articles with ambiguous content
  - Articles mentioning corruption tangentially
  - Non-English text handling (if applicable)
- [ ] Document how to run tests:
  - `uv run pytest corruption_classifier_agent/test_corruption_classifier.py -v`
  - `python corruption_classifier_agent/test_corruption_classifier.py`

### Test File Structure

```python
import pytest
from dotenv import load_dotenv
from google.adk.evaluation.agent_evaluator import AgentEvaluator

@pytest.mark.asyncio
async def test_corruption_classifier_evaluation():
    """Test the corruption_classifier_agent using the evaluation dataset.

    This test evaluates the agent's ability to:
    - Identify clear corruption/accountability cases
    - Reject non-relevant articles (sports, entertainment)
    - Handle edge cases (ambiguous content)
    - Provide appropriate confidence scores (>0.7 for relevant)
    - Return valid JSON matching ClassificationResult schema
    """
    load_dotenv("corruption_classifier_agent/.env")

    await AgentEvaluator.evaluate(
        agent_module="corruption_classifier_agent",
        eval_dataset_file_path_or_dir="corruption_classifier_agent/v1.evalset.json",
    )

if __name__ == "__main__":
    import asyncio

    async def main():
        print("Running corruption classifier evaluation...")
        await test_corruption_classifier_evaluation()
        print("Evaluation completed successfully!")

    asyncio.run(main())
```

### Acceptance Criteria

- Tests run successfully with pytest
- Can also run standalone: `python test_corruption_classifier.py`
- All evaluation cases pass
- Test output is clear and informative
- Failures provide actionable debugging information

### Dependencies

- Issue #2 (corruption classifier agent)
- Issue #4 (evaluation dataset)

---

## Issue #7: Write tests for hurricane relief classifier

**Labels:** `testing`, `phase-2`, `hurricane-relief`
**Priority:** Medium
**Estimated Effort:** 1.5 hours

### Description

Create automated tests for hurricane relief classifier using Google ADK's AgentEvaluator.

### Tasks

- [ ] Create `hurricane_relief_classifier_agent/test_hurricane_relief_classifier.py`:
  - Use `@pytest.mark.asyncio` decorator
  - Load `.env` file for API keys
  - Use `AgentEvaluator.evaluate()` with evalset
  - Support both pytest and standalone execution
- [ ] Add docstring explaining what's being tested:
  - Correctly identifies hurricane relief articles
  - Rejects non-relevant articles
  - Provides reasonable confidence scores (>0.7 for relevant)
  - Returns valid JSON matching schema
- [ ] Test edge cases:
  - Weather reports without relief funding
  - Ambiguous disaster coverage
  - Articles mentioning multiple disaster types
- [ ] Document how to run tests:
  - `uv run pytest hurricane_relief_classifier_agent/test_hurricane_relief_classifier.py -v`
  - `python hurricane_relief_classifier_agent/test_hurricane_relief_classifier.py`

### Test File Structure

Same as Issue #6, but for hurricane relief classifier.

### Acceptance Criteria

- Tests run successfully with pytest
- Can also run standalone: `python test_hurricane_relief_classifier.py`
- All evaluation cases pass
- Test output is clear and informative
- Failures provide actionable debugging information

### Dependencies

- Issue #3 (hurricane relief classifier agent)
- Issue #5 (evaluation dataset)

---

## Issue #8: Document classification criteria and usage

**Labels:** `documentation`, `phase-2`
**Priority:** Low
**Estimated Effort:** 1 hour

### Description

Create comprehensive documentation for both classifier agents covering criteria, usage, and interpretation.

### Tasks

- [ ] Create `corruption_classifier_agent/README.md`:
  - **Overview**: What the agent does
  - **Classification Criteria**: Keywords, patterns, agencies (OCG, MOCA, FID)
  - **Example Inputs/Outputs**: Real examples with explanations
  - **How to Run Evaluations**: `adk web` and pytest commands
  - **Confidence Score Interpretation**:
    - 0.9-1.0: Very high confidence (clear corruption case)
    - 0.7-0.89: High confidence (likely relevant)
    - 0.5-0.69: Medium confidence (review recommended)
    - <0.5: Low confidence (not relevant)
  - **Common False Positives/Negatives**: Known edge cases
  - **Prompt Engineering Notes**: How the prompt works
- [ ] Create `hurricane_relief_classifier_agent/README.md`:
  - Same structure as corruption classifier
  - Specific to hurricane/disaster relief domain
  - Keywords: NEMA, ODPEM, relief funding, reconstruction
- [ ] Update main project `README.md`:
  - Add "Classification Agents" section
  - Overview of both agents
  - Links to individual agent READMEs
  - How to test agents: `adk web` and pytest commands
  - Integration notes (for Phase 3 orchestrator)
- [ ] Add code comments in `agent.py` files:
  - Explain prompt structure and reasoning
  - Document key sections of instruction

### README Template Structure

```markdown
# [Agent Name] Classifier

## Overview
Brief description of what this agent does.

## Classification Criteria
- Keywords to identify
- Agencies/organizations monitored
- Types of events/issues tracked

## Example Usage

### Input
\`\`\`json
{example article JSON}
\`\`\`

### Output
\`\`\`json
{example classification result}
\`\`\`

## Running Evaluations

### Using Google ADK
\`\`\`bash
adk web
\`\`\`

### Using pytest
\`\`\`bash
uv run pytest [agent]_agent/test_[agent]_classifier.py -v
\`\`\`

## Confidence Score Interpretation
- 0.9-1.0: Very high confidence
- 0.7-0.89: High confidence (threshold)
- 0.5-0.69: Medium confidence
- <0.5: Low confidence (not relevant)

## Common Issues
- False positives: [examples]
- False negatives: [examples]
- Edge cases: [examples]

## Prompt Engineering
Explanation of how the agent's instruction prompt works.
```

### Acceptance Criteria

- Both agents have comprehensive READMEs
- Documentation includes concrete examples
- Clear guidance on running and testing agents
- Confidence score ranges are explained with examples
- Main README updated with links to agent docs
- Code comments explain prompt structure

### Dependencies

- Issue #2 (corruption classifier agent)
- Issue #3 (hurricane relief classifier agent)
- Issue #6 (corruption tests)
- Issue #7 (hurricane relief tests)

---

## Implementation Order

Follow this sequence for Phase 2:

### Step 1: Foundation
1. **Issue #1** - Create shared schemas (1 hour)

### Step 2: Corruption Classifier (Complete before Step 3)
2. **Issue #2** - Create corruption agent (2-3 hours)
3. **Issue #4** - Create corruption evaluation dataset (2 hours)
4. **Issue #6** - Write corruption tests (1.5 hours)

**Checkpoint:** Corruption classifier fully working and tested

### Step 3: Hurricane Relief Classifier
5. **Issue #3** - Create hurricane relief agent (2-3 hours)
6. **Issue #5** - Create hurricane relief evaluation dataset (2 hours)
7. **Issue #7** - Write hurricane relief tests (1.5 hours)

**Checkpoint:** Hurricane relief classifier fully working and tested

### Step 4: Documentation
8. **Issue #8** - Document both agents (1 hour)

**Phase 2 Complete:** Both classifiers ready for Phase 3 orchestrator integration

---

## Key Configuration Values

**Confidence Threshold:** 0.7 (high precision, fewer false positives)

**Model:** o4-mini (via LiteLLM)

**Input Format:** Structured `ClassificationInput` from orchestrator

**Output Format:** `ClassificationResult` with is_relevant, confidence, reasoning, key_entities

**Database Compatibility:** Output maps to `Classification` Pydantic model for persistence
