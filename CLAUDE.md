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

### Agent Architecture

The system uses a single specialized agent (`news_gatherer_agent`) that:
- Scrapes two specific Jamaica Gleaner sections: lead stories and news
- Identifies articles relevant to government accountability
- Returns structured JSON responses with relevance scoring
- Implements respectful crawling with 10-second delays

### Dependencies

- `google-adk>=1.8.0` - Google Agent Development Kit for LLM agent framework
- `litellm>=1.74.3` - LLM abstraction layer, configured to use o4-mini model
- `requests` - HTTP library for web scraping
- Python 3.12+ required

## Development Commands

### Running the Application

The README indicates the project can be run via:
```bash
adk web
```

This suggests the project is designed to work with Google ADK's web interface.

### Package Management

The project uses `uv` for dependency management:
- `uv.lock` - Lock file for reproducible builds
- `pyproject.toml` - Project configuration and dependencies

### Testing

The project includes an evaluation set (`v1.evalset.json`) for testing agent performance, though no standard test runner configuration was found.

## Important Implementation Details

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