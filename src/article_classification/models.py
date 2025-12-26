"""Classification models for article classification service."""
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, field_validator, ConfigDict, Field


class ClassifierType(str, Enum):
    """
    Types of classifiers available for article analysis.

    Each classifier focuses on a specific accountability topic:
    - CORRUPTION: Detects corruption, contract irregularities, OCG investigations
    - HURRICANE_RELIEF: Tracks disaster relief fund allocation and management

    Example:
        >>> classifier_type = ClassifierType.CORRUPTION
        >>> classifier_type.value
        'CORRUPTION'
        >>> ClassifierType.HURRICANE_RELIEF
        <ClassifierType.HURRICANE_RELIEF: 'HURRICANE_RELIEF'>
    """

    CORRUPTION = "CORRUPTION"
    HURRICANE_RELIEF = "HURRICANE_RELIEF"


class ClassificationInput(BaseModel):
    """
    Input data for article classification agents.

    This model serves as the interface between the article extraction layer
    and the classification layer. It combines content from ExtractedArticleContent
    with contextual metadata from the scraper to provide all necessary information
    for AI-based relevance classification.

    Important: Classification happens BEFORE database storage, so article_id is
    not available at this stage. The URL serves as the unique identifier.

    Workflow:
        1. Extract article content from news source → ExtractedArticleContent
        2. Construct ClassificationInput (this model) from extraction + scraper context
        3. Classify to determine relevance → ClassificationResult
        4. If relevant, store article in database (article_id generated here)

    Example:
        >>> from datetime import datetime, timezone
        >>> # After extracting article content
        >>> url = "https://jamaica-gleaner.com/article/news/20251201/gov-announces-transparency"
        >>> section = "News"  # From scraper context
        >>> extracted = await extractor.extract(url)  # Returns ExtractedArticleContent
        >>>
        >>> # Construct classification input
        >>> classification_input = ClassificationInput(
        ...     url=url,
        ...     title=extracted.title,
        ...     section=section,
        ...     full_text=extracted.full_text,
        ...     published_date=extracted.published_date,
        ... )
        >>>
        >>> # Pass to classifier
        >>> result = await corruption_classifier.classify(classification_input)
        >>>
        >>> # Only store if relevant
        >>> if result.is_relevant:
        ...     # Store article and classification in database
        ...     pass
    """

    url: str
    title: str
    section: str
    full_text: str
    published_date: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate that url is not empty and has basic URL structure."""
        if not v or not v.strip():
            raise ValueError('URL cannot be empty')

        # Basic URL validation - must start with http:// or https://
        v = v.strip()
        if not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError('URL must start with http:// or https://')

        return v

    @field_validator('title', 'section')
    @classmethod
    def validate_required_string(cls, v: str) -> str:
        """Validate that required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError('Field cannot be empty')
        return v.strip()

    @field_validator('full_text')
    @classmethod
    def validate_full_text(cls, v: str) -> str:
        """Validate that full_text is not empty and meets minimum length."""
        if not v or not v.strip():
            raise ValueError('Full text cannot be empty')

        stripped = v.strip()
        # Minimum 50 characters for meaningful content
        if len(stripped) < 50:
            raise ValueError('Full text must be at least 50 characters')

        return stripped

    @field_validator('published_date')
    @classmethod
    def validate_published_date(cls, v: datetime | None) -> datetime | None:
        """Validate that published_date is timezone-aware if provided."""
        if v is None:
            return None

        # Ensure timezone-aware datetime (consistent with existing patterns)
        if v.tzinfo is None:
            raise ValueError('Published date must be timezone-aware')

        return v


class ClassificationResult(BaseModel):
    """
    Output from article classification agents.

    This model represents the structured result returned by classifier agents
    after analyzing an article for relevance to a specific accountability topic.
    The result includes a binary relevance decision, confidence score, reasoning
    for transparency, and optionally extracted key entities.

    Workflow Position:
        Extract → ClassificationInput → Classifier Agent → **ClassificationResult** → Database

    Mapping to Database (Classification model):
        - ClassificationResult.is_relevant → Threshold logic for storage decision
        - ClassificationResult.confidence → Classification.confidence_score
        - ClassificationResult.reasoning → Classification.reasoning
        - ClassificationResult.classifier_type → Classification.classifier_type
        - ClassificationResult.model_name → Classification.model_name
        - ClassificationResult.key_entities → Not currently stored (future enhancement)

    Example:
        >>> result = ClassificationResult(
        ...     is_relevant=True,
        ...     confidence=0.85,
        ...     reasoning="Article discusses OCG investigation into contract irregularities at Ministry of Education",
        ...     key_entities=["OCG", "Ministry of Education", "Contract Irregularities"],
        ...     classifier_type=ClassifierType.CORRUPTION,
        ...     model_name="gpt-4o-mini"
        ... )
        >>> result.is_relevant
        True
        >>> result.key_entities
        ['OCG', 'Ministry of Education', 'Contract Irregularities']
        >>> result.model_name
        'gpt-4o-mini'
    """

    is_relevant: bool
    confidence: float
    reasoning: str
    key_entities: list[str] = []
    classifier_type: ClassifierType
    model_name: str

    model_config = ConfigDict(from_attributes=True)

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Validate that confidence is between 0.0 and 1.0."""
        if v < 0.0 or v > 1.0:
            raise ValueError('Confidence must be between 0.0 and 1.0')
        return v

    @field_validator('reasoning', 'model_name')
    @classmethod
    def validate_required_string(cls, v: str) -> str:
        """Validate that required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError('Field cannot be empty')
        return v.strip()

    @field_validator('key_entities')
    @classmethod
    def validate_key_entities(cls, v: list[str]) -> list[str]:
        """Validate and clean each entity in the list."""
        if not isinstance(v, list):
            raise ValueError('Key entities must be a list')

        # Strip whitespace from each entity and filter out empty strings
        cleaned = [entity.strip() for entity in v if entity and entity.strip()]
        return cleaned


class NormalizedEntity(BaseModel):
    """
    Represents a single normalized entity with its original form and normalization metadata.

    This model is used to preserve both the original entity name (as extracted from article)
    and its normalized canonical form (for deduplication) when storing entities in the database.

    This is the individual entity object that's part of EntityNormalizationResult.normalized_entities
    array. Each entity has its own confidence score and reasoning.

    Workflow Position:
        Orchestration → EntityNormalizer → list[**NormalizedEntity**] → Persistence

    Mapping to Database (Entity model):
        - NormalizedEntity.original_value → Entity.name (display name)
        - NormalizedEntity.normalized_value → Entity.normalized_name (canonical form for deduplication)
        - NormalizedEntity.confidence → Not stored (used for quality tracking/debugging)
        - NormalizedEntity.reason → Not stored (used for transparency/debugging)

    Example:
        >>> entity = NormalizedEntity(
        ...     original_value="Hon. Ruel Reid",
        ...     normalized_value="ruel_reid",
        ...     confidence=0.95,
        ...     reason="Removed title 'Hon.' and standardized format",
        ...     context=""
        ... )
        >>> entity.original_value
        'Hon. Ruel Reid'
        >>> entity.normalized_value
        'ruel_reid'
    """

    original_value: str = Field(
        ...,
        description="Original entity name as extracted from article"
    )
    normalized_value: str = Field(
        ...,
        description="Normalized canonical form for deduplication"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in normalization (0.0-1.0)"
    )
    reason: str = Field(
        ...,
        description="Explanation of normalization applied"
    )
    context: str = Field(
        default="",
        description="Optional context for normalization"
    )

    model_config = ConfigDict(from_attributes=True)

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Validate that confidence is between 0.0 and 1.0."""
        if v < 0.0 or v > 1.0:
            raise ValueError('Confidence must be between 0.0 and 1.0')
        return v

    @field_validator('original_value', 'normalized_value', 'reason')
    @classmethod
    def validate_non_empty_strings(cls, v: str) -> str:
        """Validate that required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError('Field cannot be empty')
        return v.strip()

    @field_validator('context')
    @classmethod
    def validate_context(cls, v: str) -> str:
        """Strip whitespace from context (can be empty)."""
        return v.strip() if v else ""


class EntityNormalizationResult(BaseModel):
    """
    Output schema for entity normalization agent.

    This model represents the structured result returned by the entity_normalizer
    agent after normalizing a list of entity names. It provides per-entity metadata
    including original value, normalized value, confidence, and reasoning.

    Normalization Rules Applied:
        - Lowercase everything
        - Remove titles (Mr., Hon., Minister, etc.)
        - Replace spaces with underscores
        - Preserve full names for people (e.g., "ruel_reid" not "reid")
        - Preserve acronyms (e.g., "OCG" → "ocg")
        - Standardize government entities

    Example:
        >>> result = EntityNormalizationResult(
        ...     normalized_entities=[
        ...         NormalizedEntity(
        ...             original_value="Hon. Ruel Reid",
        ...             normalized_value="ruel_reid",
        ...             confidence=0.95,
        ...             reason="Removed title 'Hon.' and standardized format",
        ...             context=""
        ...         )
        ...     ],
        ...     model_name="gpt-5-nano"
        ... )
        >>> result.normalized_entities[0].normalized_value
        'ruel_reid'
        >>> result.normalized_entities[0].confidence
        0.95
    """

    normalized_entities: list[NormalizedEntity] = Field(
        ...,
        description="List of normalized entities with per-entity metadata"
    )
    model_name: str = Field(
        ...,
        description="Model used for normalization"
    )

    model_config = ConfigDict(from_attributes=True)
