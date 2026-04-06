# Memory Issue Analysis and Solution Plan

**Date:** 2026-03-30
**Report Author:** Claude Code Analysis
**Status:** Analysis Complete - Implementation Plan Ready

---

## Executive Summary

The Maya agent's memory recall system has been experiencing **flaky/unstable behavior** where stored memories are not being recalled in subsequent conversation turns. After deep code analysis and runtime log review, we have identified **three distinct but interconnected issues** in the memory pipeline.

### Current Status of Fixes

| Issue | Status | Root Cause |
|-------|--------|------------|
| Write Path Gap | ✅ **FIXED** | `store_conversation_turn` was only called in planner flow, not chat path |
| User ID Mismatch | ✅ **FIXED** | Write used `runtime_user` fallback instead of `queued_user_id` |
| Timing/Async Issue | ✅ **FIXED** | Write wasn't awaited before resolving queue future |
| **Session Scope Storage** | ❌ **OPEN** | Memories not stored with `session_id` metadata |
| **Audit Metric Mismatch** | ❌ **OPEN** | SmartLLM counts `[Memory]` tags, but memories embedded in system content |

---

## Root Cause Analysis

### Issue 1: Session-Scoped Retrieval Fails (Primary Blocker)

**Problem:**
Retrieval with `session_id` scope returns empty because memories are stored **without** `session_id` metadata.

**Evidence from Logs:**
```
🧠 memory_retrieve_start user_id=runtime_user session_id=console-room
🧠 retriever_scope_fallback reason=session_scoped_empty user_id=runtime_user session_id=console-room
```

**Code Analysis:**

1. In `hybrid_memory_manager.py:store_conversation_turn()`, the method accepts `user_id` but **not** `session_id`:
```python
def store_conversation_turn(
    self,
    user_msg: str,
    assistant_msg: str,
    metadata: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> bool:
    # session_id is NOT a parameter!
    text = f"User: {user_msg}\nAssistant: {assistant_msg}"
    combined_metadata = metadata or {}
    if user_id:
        combined_metadata = {**combined_metadata, "user_id": user_id}
    # session_id is NEVER added to metadata
```

2. In `agent_orchestrator.py:_store_chat_turn_memory()`, `session_id` is never passed:
```python
async def _store_chat_turn_memory(self, user_text: str, response: Any, user_id: str = "console_user") -> None:
    # session_id not in signature!
    self.memory.store_conversation_turn(
        user_msg=user_text,
        assistant_msg=response_text,
        metadata={"source": "conversation", "role": "chat"},
        user_id=user_id,  # No session_id!
    )
```

3. The retriever tries to filter by `session_id`, but no memories have this metadata:
```python
@staticmethod
def _filter_by_session(
    results: List[Dict[str, Any]],
    session_id: str | None = None,
) -> List[Dict[str, Any]]:
    if not session_id:
        return results
    filtered: List[Dict[str, Any]] = []
    for result in results:
        metadata = result.get("metadata")
        if isinstance(metadata, dict) and metadata.get("session_id") == session_id:
            filtered.append(result)  # Never matches because no memories have session_id
    return filtered
```

**Impact:**
- Session-scoped retrieval returns empty
- System falls back to global retrieval (no session filter)
- Works by accident, but not architecturally correct
- Cross-session memory leakage possible

---

### Issue 2: Audit Metric Mismatch (Misleading Observability)

**Problem:**
The `smart_llm_context_audit` reports `memory_msgs=0` even when memories ARE being retrieved and injected.

**Code Analysis:**

In `smart_llm.py:347-354`:
```python
_memory_count = sum(
    1 for m in constructed_messages
    if "[Memory]" in str(getattr(m, "content", ""))
)
logger.info(
    "smart_llm_context_audit memory_msgs=%d total_msgs=%d",
    _memory_count, len(constructed_messages)
)
```

**The Problem:**
The audit looks for `"[Memory]"` in message content, but in `context_builder.py:124-131`:
```python
if self.memory_manager and self.user_id:
    try:
        memories = await self.memory_manager.get_user_context(self.user_id, k=4)
        if memories:
            system_content += f"\n\n## Retrieved Memories\n{memories}"  # No [Memory] tag!
    except Exception as e:
        logger.warning(f"Failed to inject memories: {e}")
```

Memories are embedded inside the system prompt with a `## Retrieved Memories` header, NOT as separate messages with `[Memory]` tags.

**Impact:**
- The audit metric is unreliable for debugging
- Makes it appear memories aren't working when they might be
- Wastes engineering time investigating false negatives

---

### Issue 3: Identity Query Routing (User Experience Gap)

**Problem:**
When users ask identity questions like "what do you know about me" or "what is my name", the agent doesn't prioritize memory recall.

**Evidence:**
The daily log shows a 3-turn test:
1. "my name is Harsha" → Stored ✓
2. "what is 2 plus 2" → Math question
3. "what do you know about me" → **Agent responds "I don't know anything about you"**

**Code Analysis:**
In `context_builder.py:124-131`, memory retrieval uses a **static query**:
```python
memories = await self.memory_manager.get_user_context(self.user_id, k=4)

# Which calls:
def get_user_context(self, user_id: str, k: int = 5) -> Optional[str]:
    memories = self.retrieve_relevant_memories(
        query="user information name preferences background context",  # Static!
        k=k,
        user_id=user_id,
        origin="chat",
    )
```

The query `"user information name preferences background context"` doesn't change based on what the user asked. For identity queries like "what do you know about me", the query should be the **actual user message** to get semantically relevant results.

---

### Issue 4: Context Guard Memory Detection (Possible False Positive)

**Evidence from Logs:**
```
context_guard_tokens_memory=565
```

The ContextGuard reports 565 tokens of memory budget usage, but the SmartLLM audit shows `memory_msgs=0`. This suggests memory text IS being included in the final context (hence the token count), but not as separate messages.

**Conclusion:**
Memory IS being injected into the system prompt, but the audit is looking in the wrong place.

---

## Solution Plan

### Fix 1: Store Session ID in Memory Metadata (Critical)

**Files to Modify:**
- `core/memory/hybrid_memory_manager.py`
- `core/orchestrator/agent_orchestrator.py`

**Implementation:**

1. **Update `store_conversation_turn` signature** to accept `session_id`:
```python
def store_conversation_turn(
    self,
    user_msg: str,
    assistant_msg: str,
    metadata: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,  # NEW PARAMETER
) -> bool:
    text = f"User: {user_msg}\nAssistant: {assistant_msg}"
    combined_metadata = metadata or {}
    if user_id:
        combined_metadata = {**combined_metadata, "user_id": user_id}
    if session_id:  # NEW
        combined_metadata = {**combined_metadata, "session_id": session_id}
```

2. **Update `_store_chat_turn_memory`** to pass session_id:
```python
async def _store_chat_turn_memory(
    self,
    user_text: str,
    response: Any,
    user_id: str = "console_user",
    session_id: Optional[str] = None,  # NEW PARAMETER
) -> None:
    # ...
    self.memory.store_conversation_turn(
        user_msg=user_text,
        assistant_msg=response_text,
        metadata={"source": "conversation", "role": "chat"},
        user_id=user_id,
        session_id=session_id,  # NEW
    )
```

3. **Update all call sites** to pass `session_id` from `tool_context` or `self._current_session_id`.

---

### Fix 2: Fix Audit Metric to Detect Memory in System Prompt

**File:** `core/llm/smart_llm.py`

**Implementation:**

Update the audit to detect memories embedded in system content:
```python
# OLD (looking for [Memory] tag)
_memory_count = sum(
    1 for m in constructed_messages
    if "[Memory]" in str(getattr(m, "content", ""))
)

# NEW (detecting Retrieved Memories section)
system_content_str = ""
for m in constructed_messages:
    if getattr(m, "role", None) == "system":
        system_content_str = str(getattr(m, "content", ""))
        break

# Check if Retrieved Memories section exists
_memory_section_present = "## Retrieved Memories" in system_content_str
_memory_byte_size = len(system_content_str.split("## Retrieved Memories")[1]) if _memory_section_present else 0

logger.info(
    "smart_llm_context_audit memory_msgs=%d total_msgs=%d memory_present=%s memory_bytes=%d",
    _memory_count, len(constructed_messages), _memory_section_present, _memory_byte_size
)
```

---

### Fix 3: Dynamic Memory Query Based on User Intent

**File:** `core/context/context_builder.py`

**Implementation:**

For identity queries, use the actual user message as the query:
```python
# 5. Retrieved Memories (k=4, full content)
if self.memory_manager and self.user_id:
    try:
        # Dynamic query for identity questions
        identity_patterns = (
            r"what do you know about me",
            r"what is my name",
            r"who am i",
            r"tell me about myself",
        )
        is_identity_query = any(re.search(p, message.lower()) for p in identity_patterns)

        if is_identity_query:
            # Use the actual user question as query for better semantic matching
            query = message
        else:
            # Default query for general context
            query = "user information name preferences background context"

        memories = await self.memory_manager.get_user_context(
            self.user_id,
            k=4,
            query=query,  # Pass dynamic query
        )
        if memories:
            system_content += f"\n\n## Retrieved Memories\n{memories}"
    except Exception as e:
        logger.warning(f"Failed to inject memories: {e}")
```

**Also update** `get_user_context` in `hybrid_memory_manager.py` to accept an optional query parameter:
```python
async def get_user_context(
    self,
    user_id: str,
    k: int = 5,
    query: Optional[str] = None,  # NEW PARAMETER
) -> Optional[str]:
    query = query or "user information name preferences background context"
    memories = self.retrieve_relevant_memories(
        query=query,  # Use passed query
        k=k,
        user_id=user_id,
        origin="chat",
    )
```

---

### Fix 4: Add Context Builder Memory Injection Log

**File:** `core/context/context_builder.py`

**Implementation:**

Add explicit logging to prove memory text is injected:
```python
if memories:
    system_content += f"\n\n## Retrieved Memories\n{memories}"
    logger.info(
        "context_builder_memory_injected user_id=%s memory_bytes=%d preview=%s",
        self.user_id,
        len(memories),
        memories[:200] + "..." if len(memories) > 200 else memories
    )
```

---

## Testing Strategy

### Test 1: Session ID Storage Verification
```python
def test_memory_stores_session_id():
    """Verify session_id is stored in memory metadata."""
    memory_manager.store_conversation_turn(
        user_msg="Test message",
        assistant_msg="Test response",
        user_id="test_user",
        session_id="test_session_123",
    )

    # Retrieve with session scope
    results = memory_manager.retrieve_relevant_memories(
        query="test",
        user_id="test_user",
        session_id="test_session_123",
    )

    assert len(results) > 0
    assert results[0]["metadata"]["session_id"] == "test_session_123"
```

### Test 2: Two-Turn Identity Recall Test
```python
async def test_identity_recall_across_turns():
    """Verify name is recalled in second turn."""
    # Turn 1: Store name
    await agent.process("My name is Alice")

    # Turn 2: Ask about identity
    response = await agent.process("What is my name?")

    assert "Alice" in response, f"Expected 'Alice' in response, got: {response}"
```

### Test 3: Audit Metric Verification
```python
def test_memory_audit_detects_injection():
    """Verify audit log shows memory present when injected."""
    # Process a message with memory
    with capture_logs() as logs:
        await agent.process("Remember this: test data")
        await agent.process("What do you know about me?")

    # Verify audit shows memory present
    audit_logs = [l for l in logs if "smart_llm_context_audit" in l]
    assert len(audit_logs) > 0
    assert "memory_present=True" in audit_logs[-1]
```

---

## Industry Best Practices for Python Agent Memory

Based on web research (2024-2026), here are key patterns for robust agent memory:

### 1. Memory Leak Prevention
- **Use `tracemalloc`** for line-by-line allocation tracking
- **Use `memray`** for production C-extension profiling
- **Avoid unbounded caches** — always use LRU with `functools.lru_cache`
- **Use `weakref`** for back-references to prevent cycles

### 2. Memory Architecture Patterns
| Pattern | Use Case | Implementation |
|---------|----------|----------------|
| **Short-term** | Current conversation | In-memory buffer with TTL |
| **Working** | Multi-turn context | Sliding window (last N messages) |
| **Long-term** | User facts, preferences | Vector + keyword hybrid store |
| **Episodic** | Past conversations | Session-scoped retrieval with fallback |

### 3. Retrieval Best Practices
- **Hybrid search**: Vector for semantic + keyword for exact
- **Reciprocal Rank Fusion (RRF)**: Combines multiple retrieval scores
- **Query expansion**: Use LLM to expand short queries
- **Metadata filtering**: Always filter by user_id, optionally session_id

### 4. Production Monitoring
```python
class MemoryHealthMonitor:
    """Production memory health monitoring."""

    def __init__(self):
        self.store_latency_ms = []
        self.retrieve_latency_ms = []
        self.hit_rate = 0.0

    def record_store(self, latency_ms: float):
        self.store_latency_ms.append(latency_ms)
        if len(self.store_latency_ms) > 1000:
            self.store_latency_ms = self.store_latency_ms[-1000:]

    def record_retrieve(self, latency_ms: float, hit_count: int):
        self.retrieve_latency_ms.append(latency_ms)
        self.hit_rate = 0.9 * self.hit_rate + 0.1 * (1.0 if hit_count > 0 else 0.0)
```

---

## Implementation Priority

| Priority | Fix | Effort | Impact |
|----------|-----|--------|--------|
| **P0** | Store `session_id` in memory metadata | Low | **Critical** - Fixes session-scoped retrieval |
| **P0** | Update audit metric detection | Low | **Critical** - Enables proper debugging |
| **P1** | Add context builder memory log | Low | High - Proves injection works |
| **P1** | Dynamic query for identity questions | Medium | Medium - Improves UX for common queries |
| **P2** | Memory health monitoring | Medium | Medium - Production readiness |

---

## Verification Checklist

- [ ] `session_id` is stored in memory metadata for all conversation turns
- [ ] Retrieval with `session_id` filter returns memories from that session
- [ ] SmartLLM audit correctly detects memory presence in system content
- [ ] Identity queries ("what is my name") use dynamic query for retrieval
- [ ] Context builder logs show memory bytes and preview
- [ ] Two-turn identity recall test passes
- [ ] All existing tests still pass

---

## References

1. **Daily Log 2026-03-30**: `/home/harsha/Downloads/Projects/v2/Maya-One-phase-0-2/obsidian_vault/Daily/2026-03-30.md`
2. **Hybrid Memory Manager**: `core/memory/hybrid_memory_manager.py`
3. **Agent Orchestrator**: `core/orchestrator/agent_orchestrator.py`
4. **Context Builder**: `core/context/context_builder.py`
5. **Smart LLM**: `core/llm/smart_llm.py`
6. **Hybrid Retriever**: `core/memory/hybrid_retriever.py`

---

## Web Sources

- [How to Debug Memory Leaks in Python - OneUptime](https://oneuptime.com/blog/post/2026-01-24-debug-memory-leaks-python/view)
- [How to Handle Memory Leaks in Python - OneUptime](https://oneuptime.com/blog/post/2025-01-06-python-memory-leak-debugging/view)
- [Decoding Memory Leaks in Python - CodeSolutionsHub](https://codesolutionshub.com/2024/09/10/fix-python-memory-leaks/)
- [How to Find and Fix Memory Leaks in Python - knowledgelib.io](https://knowledgelib.io/software/debugging/python-memory-leaks/2026)
- [Debugging Common Memory Leaks in Python Applications - No-Ack.org](https://no-ack.org/debugging-common-memory-leaks-in-python-applications/)

---

**Next Action:** Implement Fix 1 (session_id storage) and Fix 2 (audit metric) as they are low-effort, high-impact changes that will close the remaining memory pipeline gaps.