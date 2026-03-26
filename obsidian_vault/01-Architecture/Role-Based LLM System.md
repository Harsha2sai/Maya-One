# Role-Based LLM System

## Purpose
Provides different LLM configurations optimized for specific agent modes to improve performance and accuracy.

## Components
**RoleLLM Adapter**
- Provides different LLM configurations for different modes:
  - **CHAT**: Conversational, empathetic voice role
  - **TOOL_ACTION**: Optimized for tool execution
  - **PLANNER**: Structured task decomposition (no tool access)
  - **WORKER**: Background task execution

**SmartLLM** (`core/llm/smart_llm.py`)
- Main LLM wrapper with provider abstraction
- Handles tool schemas and response parsing
- Manages role switching

## Internal Logic
Each role has:
- Different system prompts
- Different temperature/settings
- Different tool access
- Different response format expectations

## Dependencies
- [[ToolManager]]
- [[TaskWorker]]
- [[AgentOrchestrator]]

## Related
- [[Intent-First Routing]]
- [[Execution Router]]
