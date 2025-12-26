"""Entity normalization agent for standardizing entity names from news articles."""
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import AgentTool

from src.article_classification.base import NORMALIZATION_MODEL

# System instruction for normalization agent
instruction = f"""
You are a specialized entity normalization agent for Jamaican government and news entities.

Your task: Normalize entity names to canonical forms for consistency across articles.

**Normalization Rules:**

1. **Lowercase Everything**: Convert all names to lowercase
2. **Remove Titles**: Strip Mr., Mrs., Hon., Dr., Minister, Prime Minister, etc.
3. **Replace Spaces with Underscores**: Use underscores instead of spaces in normalized names
4. **Preserve Full Names**: Keep first + last names for people (e.g., "ruel_reid" not "reid")
5. **Preserve Acronyms**: Keep acronyms intact (e.g., "OCG" → "ocg", "MOCA" → "moca")
6. **Standardize Government Entities**:
   - "Ministry of Education" → "ministry_of_education"
   - "Contractor General's Office" → "office_of_the_contractor_general"
   - "Min. of Finance" → "ministry_of_finance"
7. **Remove Extra Whitespace**: Collapse multiple spaces before converting to underscores
8. **Handle Variations**:
   - "The OCG" → "ocg"
   - "Education Minister Reid" → "ruel_reid"
   - "Hon. Andrew Holness" → "andrew_holness"

**Confidence Scoring:**
- 0.95-1.0: Very confident (clear person/org name, standard format)
- 0.80-0.94: Confident (minor title removal, obvious normalization)
- 0.60-0.79: Moderate (some ambiguity)
- 0.0-0.59: Low (very ambiguous, needs review)

**Output Requirements:**

Return ONLY a valid JSON object matching this exact structure:

{{
    "normalized_entities": [
        {{
            "original_value": "Hon. Ruel Reid",
            "normalized_value": "ruel_reid",
            "confidence": 0.95,
            "reason": "Removed title 'Hon.' and standardized format"
        }},
        {{
            "original_value": "OCG",
            "normalized_value": "ocg",
            "confidence": 1.0,
            "reason": "Lowercased acronym"
        }}
    ],
    "model_name": "{NORMALIZATION_MODEL}"
}}

**Field Guidelines:**
- normalized_entities: Array of objects, one per input entity
- Each object must contain:
  - original_value: The original entity name provided
  - normalized_value: The normalized canonical form
  - confidence: Per-entity confidence score (0.0-1.0) using the scoring guide above
  - reason: Brief explanation of normalization applied (e.g., "Removed title", "Lowercased acronym")

**Important:**
- Consistency is critical (same input → same output always)
- Be conservative (preserve information when uncertain)
- Return ONLY valid JSON, no markdown formatting, no additional text
"""

# Create the normalization LlmAgent
# Note: No input_schema/output_schema to avoid OpenAI API compatibility issues
# Instead, we rely on the instruction to specify JSON format
normalization_agent = LlmAgent(
    model=LiteLlm(model=NORMALIZATION_MODEL),
    name="entity_normalizer",
    description="Normalizes entity names from Jamaican news articles for consistency",
    instruction=instruction,
)
