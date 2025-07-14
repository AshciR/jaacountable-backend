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

3. **Activate the virtual environment**:
   ```bash
   source .venv/bin/activate  # On macOS/Linux
   # or
   .venv\Scripts\activate     # On Windows
   ```

## How to Run

### Via Web Interface (Recommended)

Launch the Google ADK web interface:

```bash
adk web
```

This will start a web interface where you can interact with the news gathering agent.

## Project Architecture

```
jaacountable-backend/
├── main.py                           # Entry point
├── gleaner_researcher_agent/         # Core agent system
│   ├── __init__.py                   # Module initialization
│   ├── agent.py                      # Main LLM agent definition
│   ├── tools.py                      # Web scraping tools
│   └── v1.evalset.json              # Evaluation dataset
├── pyproject.toml                    # Project configuration
├── uv.lock                          # Dependency lock file
└── README.md                        # This file
```

### Key Components

- **`agent.py`**: Defines the `news_gatherer_agent` that orchestrates the news collection process
- **`tools.py`**: Contains web scraping functions for Jamaica Gleaner sections with built-in rate limiting
- **`v1.evalset.json`**: Evaluation dataset for testing and improving agent performance

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
- **Ethical Web Scraping**: 10-second delays between requests to respect the target website

## Contributing

When contributing to this project, please ensure:
- Maintain the 10-second crawl delay in scraping functions
- Follow the existing agent prompt structure
- Add new evaluation cases to the evalset when adding features
- Keep the focus on government accountability topics