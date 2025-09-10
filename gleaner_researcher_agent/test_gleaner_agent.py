"""Tests for the gleaner_researcher_agent using Google ADK AgentEvaluator."""

import pytest
from dotenv import load_dotenv
from google.adk.evaluation.agent_evaluator import AgentEvaluator


@pytest.mark.asyncio
async def test_gleaner_agent_evaluation():
    """Test the gleaner_researcher_agent using the existing evaluation dataset.
    
    This test evaluates the agent's ability to:
    - Scrape Jamaica Gleaner lead stories and news sections
    - Identify articles relevant to government accountability
    - Return structured JSON responses with relevance scoring
    """
    # Load environment variables
    load_dotenv("gleaner_researcher_agent/.env")
    
    await AgentEvaluator.evaluate(
        agent_module="gleaner_researcher_agent",
        eval_dataset_file_path_or_dir="/Users/richie/Development/python-projects/jaacountable-backend/gleaner_researcher_agent/v1.evalset.json",
    )

if __name__ == "__main__":
    # Allow running the test directly with: python test_gleaner_agent.py
    import asyncio
    
    async def main():
        print("Running gleaner_researcher_agent evaluation...")
        await test_gleaner_agent_evaluation()
        print("Evaluation completed successfully!")
    
    asyncio.run(main())
