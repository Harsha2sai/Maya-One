# ContextBuilder

## Responsibility
Build LLM-ready message context with intent-based tool filtering, memory retrieval, and token budget management.

## Core Flow
```
User message → Intent classification → Tool filtering → System prompt selection → Memory retrieval → Message assembly → Token guard
```

## Intent-based Tool Filtering (PHASE 4 Optimization)

### Small-Talk Detection
```python
if is_small_talk(message):
    tools = []  # Zero tools for chat
    system_prompt = "You are Maya, helpful and friendly"
```
**Token savings**: 1500-2000 tokens per chat query

### Task Request Detection
```python
elif intent == "task_request":
    tools = all_tools  # Full toolset
```
**Enables**: Decomposition, planning, execution

### General Query (Default)
```python
else:
    tools = essential_tools  # Limited subset
    essential_keywords = ["web_search", "weather", "time", "date"]
```
**Results**: 3-5 tools instead of 20+

## System Prompt Selection

### Chat Mode (is_small_talk)
Minimal prompt with identity only:
```
You are Maya, a helpful AI assistant. Keep responses friendly and concise.
```
**Purpose**: Fast responses for greetings, small talk, identity questions

### Tool Mode (intent == "task_request")
Planner-level prompt:
```
You are Maya, planning and execution assistant. Access full toolset.
Break complex requests into atomic steps.
```
**Features**:
- Task decomposition
- Tool selection
- Parameter inference

### General Mode
Standard agent prompt:
```
You are Maya, knowledgeable assistant. Use provided tools as needed.
Answer user's question directly.
```

## Memory Retrieval Integration

### Rolling Context Manager
```python
if rolling_manager and chat_ctx:
    await rolling_manager.update_session(chat_ctx)
```
**Purpose**: Maintains conversational context across turns

### Memory Query Decision
Small talk queries bypass memory retrieval:
```python
if is_chat:
    memory_facts = []  # No retrieval
else:
    memory_facts = await memory_manager.fetch_relevant_facts(...)
```
**Latency saved**: 200-500ms per small-talk query

## Message Assembly (LRCS Protocol)

### LRCS = Lifecycle + Rolling + Context + System

1. **Lifecycle Phase Hooks**: Not explicitly added yet (reserved)
2. **Rolling Summary**: Added by RollingContextManager
3. **Context Window**: User + assistant message history
4. **System Prompt**: Selected based on intent

## Token Budget Management

### Initial Budgets (PHASE 6 Tuning)
- **Overall budget**: `< 2000 tokens` (down from 12000)
- **Tool overhead**: 50 tokens base + 20-50 per tool
- **Memory facts**: 50-300 tokens depending on relevance
- **Context history**: Managed by ContextGuard

### ContextGuard Enforcement
```python
guard = ContextGuard()
# Enforces token limits per component
guard.check_tool_bloat(tool_count)
guard.check_memory_bloat(memory_fact_count)
```

## Edge Case Handling

### Tool Schema Fallback
If no tools match essential keywords:
```python
if not essential_tools:
    tools = all_tools  # Fallback
```

### Inline Context Removal (PHASE 6)
Removed inline content that bloated contexts:
- No raw memory chunks dumped inline
- Facts are integrated via ContextGuard
- System prompt explicitly guides appropriate tool use

### Identity Question Detection
Pattern regex detection for efficiency:
```python
IDENTITY_PATTERNS = (
    r"\b(what(?:'s| is)\s+your\s+name|who\s+are\s+you)\b",
)
```

## Hybrid Memory Integration

### Vector + FTS5 Search
```python
hybrid_results = await memory_manager.hybrid_search(
    query=message,
    top_k=4 if intent == "task" else 2
)
```

### Memory Fact Insertion
Facts integrated as system messages:
```python
for fact in memory_facts:
    messages.append(ChatMessage(
        role="system",
        content=f"[Memory] {fact['content']} (relevance: {fact['score']})"
    ))
```

## Performance Metrics

### Token Usage by Intent
- **Small talk**: ~200 tokens (no tools, minimal context)
- **General query**: ~1200 tokens (3-5 tools, moderate context)
- **Task request**: ~1800 tokens (all tools, full context)

### Latency Improvements
- **First token**: 3.8s → 1.2s for chat queries (68% improvement)
- **Tool filtering**: Saves 500-800ms by reducing token generation
- **Memory bypass**: Saves 200-500ms for small talk

## Integration Points
- **AgentOrchestrator** → Provides message and chat_ctx
- **MemoryManager** → Returns relevant facts
- **ToolManager** → Returns available tools
- **RollingContextManager** → Maintains session state
- **ContextGuard** → Enforces token budgets
- **Agent** → Receives final message list

## Known Issues

### Token Bloat (PHASE 6)
**Status**: Partially fixed
- Removed inline context fallback
- Reduced token budget to < 2000
- **Remaining**: Memory retrieval still adds excessive tokens in some cases

### FTS5 Memory Search Running Unnecessarily
**Status**: Mitigated
Small talk now bypasses memory entirely. General queries still trigger search.

### Schema Mismatch with LiveKit
**Status**: Ongoing
ContextBuilder must handle tool schema inconsistencies between different LLM providers.

## Related Files
- `Agent/core/context/context_builder.py`
- `Agent/core/context/final_context_guard.py`
- `Agent/core/context/token_budget_guard.py`
- `Agent/core/context/rolling_summary.py`
- `Agent/core/utils/small_talk_detector.py`
- `Agent/core/utils/intent_utils.py`

## Related Components
- [[Context Guard and Tool Safety]]
- [[Context Builder Token Bloat]]
- [[FTS5 Memory Search Running Unnecessarily]]
- [[ToolManager]]
- [[AgentOrchestrator]]
- [[Role-Based LLM System]]
