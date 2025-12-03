# Google ADK Framework - Learning Summary

This document summarizes key concepts and patterns from Google's Agent Development Kit (ADK) documentation.

## 1. Core Agent Architecture

### LlmAgent Fundamentals

LLM agents are the "thinking" components that leverage Large Language Models for reasoning and decision-making. Unlike deterministic workflow agents, LLM agents exhibit non-deterministic behavior.

**Essential Configuration Components:**

```python
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

agent = LlmAgent(
    name="agent_name",           # Required: Unique identifier for multi-agent systems
    description="...",            # Concise capability summary (used for routing)
    model=LiteLlm(model="gemini-2.0-flash"),
    instruction="...",            # Most critical: defines behavior, constraints, output
    tools=[tool1, tool2],         # Optional: Extend agent capabilities
    output_schema=MySchema,       # Optional: Enforce structured JSON output
    output_key="result"           # Optional: Persist results to session state
)
```

### The `instruction` Parameter

The instruction is the **most critical element**. It should communicate:
- Core task and goal
- Desired personality or persona
- Behavioral constraints
- When and how to use tools
- Expected output format

**Dynamic Value Insertion:**
- `{var}` - Insert state variables
- `{artifact.var}` - Insert artifact content

### Output Schema & Structure

When `output_schema` is defined:
- Agent's final response **must** be a JSON string conforming to schema
- **Tools are disabled** when output formatting is paramount
- Use Pydantic models for type-safe schemas

### Context Management

The `include_contents` parameter controls history access:
- **Default**: Agent receives relevant conversation history
- **'none'**: Agent operates stateless (current instruction and input only)

---

## 2. Tool Integration

Tools extend agent capabilities beyond built-in LLM knowledge.

**Implementation Options:**

1. **Native Python Functions** (automatically wrapped):
```python
def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Weather in {city}: Sunny, 72°F"

agent = LlmAgent(tools=[get_weather])
```

2. **Custom Classes** inheriting from `BaseTool`:
```python
from google.adk.tools import BaseTool

class WeatherTool(BaseTool):
    def execute(self, city: str) -> str:
        return f"Weather in {city}: Sunny, 72°F"
```

3. **Agent Instances** (enabling delegation):
```python
specialist_agent = LlmAgent(name="specialist", ...)
coordinator_agent = LlmAgent(tools=[specialist_agent], ...)
```

**How Tools Work:**
- LLM uses function/tool names, descriptions, and parameter schemas
- Decides which tool to call based on conversation and instructions
- Tool results are returned to agent context

---

## 3. Multi-Agent Systems

### Architecture Pattern

Multi-agent systems use **parent-child hierarchies**:

```python
child_agent1 = LlmAgent(name="child1", ...)
child_agent2 = LlmAgent(name="child2", ...)

parent_agent = LlmAgent(
    name="parent",
    sub_agents=[child_agent1, child_agent2]
)
```

**Important Constraint:** An agent instance can only have **one parent** (or `ValueError` occurs).

### Communication Mechanisms

**1. Shared Session State**

Agents share a `Session` object within the same invocation:

```python
# Agent 1 writes
context.state["result"] = {"status": "complete"}

# Agent 2 reads (in subsequent execution)
previous_result = context.state.get("result")
```

**2. LLM-Driven Delegation**

Agents intelligently route tasks using function calls:

```python
# In agent instructions:
"Use transfer_to_agent(agent_name='specialist') to delegate complex tasks"

# Framework intercepts this call and switches execution
```

**Requirements:**
- Clear `instructions` on when to transfer
- Distinct `description` fields for routing decisions

**3. Explicit Invocation via AgentTool**

Wrap agents as callable tools:

```python
from google.adk.tools import AgentTool

specialist = LlmAgent(name="specialist", ...)
specialist_tool = AgentTool(specialist)

coordinator = LlmAgent(tools=[specialist_tool], ...)
```

When LLM calls the tool, framework executes agent and returns results.

---

## 4. Workflow Orchestration

### SequentialAgent

Executes sub-agents in order with shared context:

```python
from google.adk.agents import SequentialAgent

pipeline = SequentialAgent(
    sub_agents=[agent1, agent2, agent3]
)
```

- Earlier agents' results inform later steps via shared state
- Passes same context sequentially

### ParallelAgent

Runs multiple sub-agents concurrently:

```python
from google.adk.agents import ParallelAgent

parallel = ParallelAgent(
    sub_agents=[agent1, agent2, agent3]
)
```

- Distinct contextual branches (`ParentBranch.ChildName`)
- All access identical shared session state
- Enables independent parallel work with result aggregation

### LoopAgent

Repeats sub-agents sequentially:

```python
from google.adk.agents import LoopAgent

loop = LoopAgent(
    sub_agents=[agent1, agent2],
    max_iterations=5
)
```

- Terminates when `max_iterations` reached
- Or when agent escalates via `Event` with `escalate=True`

---

## 5. Common Multi-Agent Patterns

### Coordinator/Dispatcher Pattern

Central LLM agent routes requests to specialized sub-agents:

```python
corruption_agent = LlmAgent(name="corruption", description="Analyzes corruption-related articles")
hurricane_agent = LlmAgent(name="hurricane", description="Analyzes hurricane relief articles")

coordinator = LlmAgent(
    name="coordinator",
    instruction="Route articles to appropriate classifier based on content",
    sub_agents=[corruption_agent, hurricane_agent]
)
```

**Routing Methods:**
- LLM-driven delegation (`transfer_to_agent`)
- Explicit tool invocation (AgentTool wrapper)

### Sequential Pipeline

Data flows through ordered agents:

```python
extract_agent = LlmAgent(name="extract", output_key="extracted_data", ...)
classify_agent = LlmAgent(name="classify", output_key="classification", ...)
store_agent = LlmAgent(name="store", ...)

pipeline = SequentialAgent(sub_agents=[extract_agent, classify_agent, store_agent])
```

- Each writes to distinct state keys
- Downstream agents consume upstream results

### Parallel Fan-Out/Gather

Independent concurrent tasks with result synthesis:

```python
agent1 = LlmAgent(name="task1", output_key="result1", ...)
agent2 = LlmAgent(name="task2", output_key="result2", ...)
gather_agent = LlmAgent(name="gather", ...)

parallel = ParallelAgent(sub_agents=[agent1, agent2])
pipeline = SequentialAgent(sub_agents=[parallel, gather_agent])
```

### Hierarchical Task Decomposition

Multi-level agent trees recursively break complex goals:

```python
specialist1 = LlmAgent(name="specialist1", ...)
specialist2 = LlmAgent(name="specialist2", ...)

coordinator = LlmAgent(
    name="coordinator",
    sub_agents=[specialist1, specialist2]
)

orchestrator = LlmAgent(
    name="orchestrator",
    sub_agents=[coordinator]
)
```

### Generator-Critic (Iterative Refinement)

One agent generates, another reviews:

```python
generator = LlmAgent(name="generator", output_key="draft", ...)
critic = LlmAgent(name="critic", output_key="feedback", ...)

loop = LoopAgent(
    sub_agents=[generator, critic],
    max_iterations=3
)
```

- Agent reads and overwrites shared state values
- Continues until quality thresholds met

---

## 6. Best Practices

### 1. Clear Descriptions

Maintain distinct `description` fields on agents for effective LLM routing:

```python
agent = LlmAgent(
    name="corruption_classifier",
    description="Analyzes articles for corruption, bribery, and government misconduct"
)
```

### 2. Leverage output_key

Use `output_key` on `LlmAgent` instances to automatically persist results:

```python
agent = LlmAgent(
    name="classifier",
    output_key="classification_result",  # Auto-saves to context.state
    ...
)
```

Reduces boilerplate for state management.

### 3. Distinct State Keys in Parallel

Use unique state keys in parallel workflows to prevent race conditions:

```python
agent1 = LlmAgent(output_key="agent1_result", ...)
agent2 = LlmAgent(output_key="agent2_result", ...)
```

### 4. Instruction Design

- **Clear and specific** instructions with examples
- **Few-shot learning** significantly improves performance
- **Explain contextual tool usage**, don't just list tools

### 5. Schema Constraints Trade-off

When using `output_schema`:
- ✅ Enforces structured output
- ❌ **Disables tool usage**

Choose based on requirements.

### 6. Hierarchy Structure

Structure should reflect problem decomposition, not artificial nesting:

```python
# Good: Reflects actual workflow
pipeline = SequentialAgent(sub_agents=[extract, classify, store])

# Bad: Unnecessary nesting
wrapper = SequentialAgent(sub_agents=[
    SequentialAgent(sub_agents=[extract]),
    SequentialAgent(sub_agents=[classify]),
    SequentialAgent(sub_agents=[store])
])
```

---

## 7. Development Workflow

### Setup

```bash
# Install Google ADK
pip install google-adk

# Launch development UI
adk web  # http://localhost:8000

# Run agent in terminal
adk run my_agent

# Start API server
adk api_server
```

### Authentication

**Option 1: Google AI Studio**

```bash
# .env file
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=YOUR_API_KEY
```

**Option 2: Vertex AI**

```bash
# .env file
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
GOOGLE_CLOUD_LOCATION=LOCATION
```

### Project Structure

```
parent_folder/
    my_agent/
        __init__.py
        agent.py
        tools.py (optional)
        .env
```

---

## 8. Advanced Features

### Planning

Two planner implementations:

1. **BuiltInPlanner**: Leverages Gemini's thinking features
   - Configurable thinking budgets

2. **PlanReActPlanner**: Structured model output
   - PLANNING, ACTION, REASONING, FINAL_ANSWER sections

### Code Execution

Optional `code_executor` parameter allows agents to execute code blocks within LLM responses.

### LLM Generation Control

`generate_content_config` adjusts parameters:
- `temperature`
- `max_output_tokens`
- `safety_settings`

---

## 9. Session & Execution

Agents operate within sessions:

```python
from google.adk.sessions import InMemorySessionService

session_service = InMemorySessionService()
```

The `Runner` class orchestrates agent execution:
- Handles event streaming
- Manages state across interactions

---

## 10. Dev UI Features

The development UI (`adk web`) provides:
- **Event Inspection**: View all agent events and tool calls
- **Trace Logging**: Analyze latency and performance
- **Voice/Video Streaming**: Support for compatible Gemini models
- **Interactive Testing**: Test agents with different prompts

---

## Key Takeaways for Classification Interface

Based on ADK patterns, our classification system could use:

1. **Coordinator/Dispatcher Pattern**: Route articles to specialized classifiers
2. **LlmAgent with output_schema**: Use `ClassificationResult` as structured output
3. **Separate Agent Modules**: Follow `gleaner_researcher_agent/` pattern
4. **Shared State**: Pass `ClassificationInput` via `context.state`
5. **LLM-Driven Delegation**: Let coordinator intelligently route based on content
6. **Extensibility**: Add new classifiers by extending `ClassifierType` enum and creating new agent modules

### Architecture Example

```python
# corruption_classifier/agent.py
corruption_classifier = LlmAgent(
    name="corruption_classifier",
    description="Analyzes articles for corruption, bribery, and government misconduct",
    model=LiteLlm(model="gemini-2.0-flash"),
    instruction="Analyze the article and determine relevance to corruption...",
    output_schema=ClassificationResult
)

# hurricane_relief_classifier/agent.py
hurricane_classifier = LlmAgent(
    name="hurricane_relief_classifier",
    description="Analyzes articles about hurricane disaster relief and aid distribution",
    model=LiteLlm(model="gemini-2.0-flash"),
    instruction="Analyze the article and determine relevance to hurricane relief...",
    output_schema=ClassificationResult
)

# classification_coordinator/agent.py
coordinator = LlmAgent(
    name="classification_coordinator",
    description="Routes articles to appropriate topic classifiers",
    model=LiteLlm(model="gemini-2.0-flash"),
    instruction="Based on article content, delegate to appropriate classifier...",
    sub_agents=[corruption_classifier, hurricane_classifier]
)
```

This aligns with:
- ✅ Existing `ClassificationInput`/`ClassificationResult` models
- ✅ Intelligent routing requirement
- ✅ Separate agent modules organization
- ✅ Google ADK best practices
