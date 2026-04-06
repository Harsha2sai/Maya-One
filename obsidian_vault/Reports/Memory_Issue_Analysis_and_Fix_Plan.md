# Memory Pipeline Issue Analysis and Fix Plan

**Date:** 2026-03-30
**Status:** P11-02 Active - Root Cause Identified
**Author:** Claude Code Analysis

---

## Executive Summary

The agent's memory recall pipeline has structural gaps that prevent user identity and conversation context from being retained across turns. While the storage path is now functioning, **session-scoped retrieval fails** because conversation memories are stored without `session_id` metadata, and the SmartLLM audit metric **does not accurately detect memory presence** in the final LLM context.

---

## Current Issue Status (from Daily Log 2026-03-30)

### ✅ Fixed Components
1. **Memory write timing** - Awaited before queue future resolution (commit `94361fa`)
2. **user_id alignment** - Write/read key consistency fixed (commit `f526408`)
3. **Retrieval pipeline** - Returns memories after user-scoped fallback
4. **VectorStore persistence** - Confirmed persistent at `~/.maya/memory/chroma` (3555 items)

### ❌ Broken Components
1. **Session-scoped retrieval** - Always empty because memories lack `session_id` metadata
2. **SmartLLM audit metric** - `memory_msgs=0` even when memory text is present
3. **End-user answer quality** - "I don't know anything about you" despite stored memories

---

## Root Cause Analysis

### Issue 1: Session Metadata Not Stored

**Problem:** The `_store_chat_turn_memory()` method does not receive or store the `session_id` in memory metadata.

**Evidence from code:**
```python
# core/orchestrator/agent_orchestrator.py:3508-3513
self.memory.store_conversation_turn(
    user_msg=user_text,
    assistant_msg=response_text,
    metadata={"source": "conversation", "role": "chat"},
    user_id=user_id,
    # MISSING: session_id is not passed!
)
```

**Impact:** The hybrid retriever's `_filter_by_session()` method filters by `session_id`, but since stored memories have no `session_id` in metadata, session-scoped queries return empty:

```python
# core/memory/hybrid_retriever.py:59
if isinstance(metadata, dict) and metadata.get("session_id") == session_id:
    filtered.append(result)
```

**Log evidence from daily entry:**
```
Retrieval on turn 3 showed:
- session scoped query (session_id=console-room) -> count=0
- scope fallback (session_id=none) -> count=4
```

### Issue 2: Audit Metric Mismatch

**Problem:** The SmartLLM audit metric looks for `[Memory]` tag in message content, but the ContextBuilder injects memories into `system_content` without this tag.

**SmartLLM audit code:**
```python
# core/llm/smart_llm.py:347-354
_memory_count = sum(
    1 for m in constructed_messages
    if "[Memory]" in str(getattr(m, "content", ""))
)
logger.info(
    "smart_llm_context_audit memory_msgs=%d total_msgs=%d",
    _memory_count, len(constructed_messages)
)
```

**ContextBuilder injection code:**
```python
# core/context/context_builder.py:124-131
if self.memory_manager and self.user_id:
    try:
        memories = await self.memory_manager.get_user_context(self.user_id, k=4)
        if memories:
            system_content += f"\n\n## Retrieved Memories\n{memories}"
    except Exception as e:
        logger.warning(f"Failed to inject memories: {e}")
```

**The mismatch:** Memories are embedded inside `system_content` under `## Retrieved Memories` section - they are NOT separate message objects with `[Memory]` tags. Therefore:
- `memory_msgs=0` is reported (no messages contain "[Memory]")
- But memory text IS in the system prompt (explaining the 565 token context_guard_memory_tokens)

### Issue 3: Session-scoped Query Chain

**Current flow:**
1. Orchestrator calls `retrieve_relevant_memories(session_id=memory_session_id)`
2. HybridRetriever tries session-scoped filtering first
3. No memories have matching `session_id` metadata
4. Falls back to user-scoped (no session filter)
5. Returns results with fallback logged

**The fallback works, but:**
- Adds latency (two queries instead of one)
- Session-level isolation is broken (any user memory could interfere)
- Context is not properly bound to the conversation session

---

## Verification Steps Completed

| Check | Status | Evidence |
|-------|--------|----------|
| Write path functional | ✅ | `Stored conversation memory: ...` logs |
| user_id tagging works | ✅ | `Items with user_id=runtime_user: 2` probe |
| Persistence confirmed | ✅ | collection count=3555, ephemeral_fallback=False |
| Retrieval returns data | ✅ | `memory_retrieve_results count=4` logs |
| Write awaited before next turn | ✅ | 3-turn log shows proper sequencing |
| Session metadata missing | ❌ | session scoped query returns count=0 |
| Audit metric inaccurate | ❌ | memory_msgs=0 despite memory tokens=565 |
| End-user answer incorrect | ❌ | "I don't know anything about you" |

---

## Web Research: Best Practices for Agent Memory Systems

### Source: KnowledgeLib.io (2026) - Python Memory Leak Debugging

**For long-running Python agents:**

1. **Confirm leaks with `tracemalloc`** - Two snapshots and compare for allocation sites
2. **C Extension blindspot** - `tracemalloc` is Python-only; use `memray` for native allocations
3. **Detect cycles with `gc.set_debug(gc.DEBUG_SAVEALL)`** - Reveals uncollectable cycles
4. **Key constraint** - "gc.collect() cannot fix straight references—only handles cycles"
5. **Production monitoring** - Bloomberg's `memray` for production deployments
6. **Three dominant causes**:
   - Unbounded caches/lists (enforce LRU limits)
   - Reference cycles with `__del__` (replace with `weakref.finalize`)
   - Global mutable state accumulating across requests

**Application to Agent Memory:**
- Memory storage should use bounded collections (ChromaDB has HNSW limits)
- Avoid `__del__` in memory-related classes (use explicit cleanup methods)
- Monitor memory growth across conversation turns

### Source: No-Ack.org (2024) - Debugging Common Memory Leaks

**Most common causes ranked:**
1. **Unbounded caches/lists/dicts** (~25%) - *Not applicable: ChromaDB is bounded*
2. **Reference cycles with `__del__`** (~15%) - *Check MemoryItem and HybridRetriever*
3. **Global/class-level mutable state** (~15%) - *Review HybridMemoryManager singletons*
4. **Closures capturing large objects** (~10%) - *Check async callback chains*

**WeakRef Pattern for Agent Memory:**
```python
import weakref

class MemoryBackedAgent:
    def __init__(self, parent_session=None):
        # Weak reference prevents circular dependency
        self._session = weakref.ref(parent_session) if parent_session else None

    @property
    def session(self):
        return self._session() if self._session else None
```

### Source: CodeSolutionsHub (2024) - Fix Python Memory Leaks

**Key constraints:**
- `tracemalloc` doesn't track C extensions (numpy, ChromaDB native code)
- `del` doesn't free memory immediately - only decrements refcount
- Never disable GC without a plan - causes cyclic garbage accumulation

**Production Monitoring Pattern:**
```python
import tracemalloc
import gc

class MemoryLeakDetector:
    def __init__(self, interval=60, growth_threshold_mb=10):
        self.interval = interval
        self.threshold = growth_threshold_mb * 1024 * 1024
        self._baseline = None

    def start(self):
        tracemalloc.start(25)  # Store 25 frames
        self._baseline = tracemalloc.take_snapshot()
        # ... monitoring thread
```

---

## Detailed Fix Plan

### Phase A: Session Metadata Persistence (Priority: Critical)

**File:** `core/orchestrator/agent_orchestrator.py`

**A1. Update `_store_chat_turn_memory` signature and calls:**
```python
async def _store_chat_turn_memory(
    self,
    user_text: str,
    response: Any,
    user_id: str = "console_user",
    session_id: Optional[str] = None,  # ADD THIS
) -> None:
    ...
    self.memory.store_conversation_turn(
        user_msg=user_text,
        assistant_msg=response_text,
        metadata={
            "source": "conversation",
            "role": "chat",
            "session_id": session_id,  # ADD THIS
        },
        user_id=user_id,
    )
```

**A2. Update the two call sites (around lines 3474 and 4111):**
```python
# Pass session_id from context
await self._store_chat_turn_memory(
    queued_message,
    response,
    user_id=queued_user_id,
    session_id=session_id,  # ADD THIS
)
```

### Phase B: Audit Metric Accuracy (Priority: High)

**File:** `core/llm/smart_llm.py`

**B1. Add context-builder logging to prove memory injection:**
```python
# After context_builder call (around line 320-330)
if isinstance(res, tuple):
    constructed_messages, dynamic_tools = res

# ADD: Log system content memory presence
system_msg = next((m for m in constructed_messages if m.role == "system"), None)
if system_msg:
    has_memory_section = "## Retrieved Memories" in str(getattr(system_msg, "content", ""))
    logger.info(f"smart_llm_memory_section_present present={has_memory_section}")
```

**B2. Update audit metric to detect memory in system prompt:**
```python
# REPLACE lines 347-354 with:
_memory_in_system = False
system_msg = next((m for m in constructed_messages if m.role == "system"), None)
if system_msg:
    content = str(getattr(system_msg, "content", ""))
    _memory_in_system = "## Retrieved Memories" in content

logger.info(
    "smart_llm_context_audit memory_in_system=%s total_msgs=%d",
    _memory_in_system, len(constructed_messages)
)
```

### Phase C: Identity Query Routing (Priority: Medium)

**File:** `core/context/context_builder.py`

**C1. Add deterministic identity-memory routing:**
```python
IDENTITY_QUERY_PATTERNS = (
    r"\b(what do you know about me|what is my name|who am i)\b",
    r"\b(tell me about myself|remind me who i am)\b",
)

async def __call__(self, message: str, chat_ctx: ChatContext, **kwargs):
    # ... existing code ...

    # C2. Enhanced memory retrieval for identity queries
    is_identity_query = any(
        re.search(pattern, message.lower())
        for pattern in IDENTITY_QUERY_PATTERNS
    )

    if self.memory_manager and self.user_id:
        try:
            # For identity queries, use more specific retrieval
            query = (
                "my name is what who am i user identity"
                if is_identity_query
                else "user information name preferences background context"
            )
            memories = await self.memory_manager.get_user_context(self.user_id, k=4)

            if memories:
                system_content += f"\n\n## Retrieved Memories\n{memories}"

                # ADD: Explicit identity instruction for identity queries
                if is_identity_query:
                    system_content += "\n\nIMPORTANT: Use the Retrieved Memories above to answer the user's question about themselves."
            elif is_identity_query:
                system_content += "\n\nNo prior memory about this user was found."

        except Exception as e:
            logger.warning(f"Failed to inject memories: {e}")
```

### Phase D: Testing and Validation (Priority: Critical)

**D1. Create targeted test:**
```python
# tests/test_memory_session_integration.py
import pytest
from core.memory.hybrid_memory_manager import HybridMemoryManager

@pytest.mark.asyncio
async def test_memory_session_persistence():
    manager = HybridMemoryManager()

    # Store with session_id
    manager.store_conversation_turn(
        user_msg="my name is Alice",
        assistant_msg="Nice to meet you Alice!",
        metadata={"session_id": "test-session-123"},
        user_id="test_user",
    )

    # Retrieve with session scope
    memories = manager.retrieve_relevant_memories(
        query="what is my name",
        user_id="test_user",
        session_id="test-session-123",  # Should now work
    )

    assert len(memories) > 0
    assert "Alice" in memories[0].get("text", "")
```

**D2. Three-turn validation scenario:**
```
Turn 1: "my name is Harsha"
Expected: Memory stored with session_id

Turn 2: "what is 2 plus 2"
Expected: No identity recall needed

Turn 3: "what do you know about me"
Expected: "I know your name is Harsha..."
```

---

## Testing Commands

### Unit Tests
```bash
# Run memory-specific tests
pytest tests/test_hybrid_memory_manager.py -v
pytest tests/test_context_builder.py -v
pytest tests/test_hybrid_retriever.py -v
```

### Integration Test
```bash
# Three-turn console smoke test
cd /home/harsha/Downloads/Projects/v2/Maya-One-phase-0-2/Agent
python -c "
import asyncio
from core.memory.hybrid_memory_manager import HybridMemoryManager

async def test():
    manager = HybridMemoryManager()

    # Store with session
    manager.store_conversation_turn(
        'my name is TestUser',
        'Hello TestUser!',
        metadata={'session_id': 'test-session'},
        user_id='test_user'
    )

    # Retrieve scoped
    memories = manager.retrieve_relevant_memories(
        'what is my name',
        user_id='test_user',
        session_id='test-session'
    )
    print(f'Found {len(memories)} memories')
    for m in memories:
        print(f'  - {m.get(\"text\", \"\")[:100]}')

asyncio.run(test())
"
```

### Live Runtime Verification
```bash
# Check logs for new audit format
tail -f logs/agent.log | grep -E "(memory_session|smart_llm_memory_section_present)"

# Run three-turn test and capture
python agent.py --console 2>&1 | tee /tmp/memory_test_$(date +%Y%m%d_%H%M%S).log
```

---

## Success Criteria

| Metric | Before | After | How to Verify |
|--------|--------|-------|---------------|
| Session-scoped retrieval | count=0 | count>0 | Log: `memory_retrieve_results session_id=X count=Y` |
| Audit accuracy | memory_msgs=0 | memory_in_system=true | Log: `smart_llm_memory_section_present present=True` |
| User identity recall | "I don't know" | "Your name is..." | Console output on turn 3 |
| Session metadata in stored items | Missing | Present | Direct ChromaDB inspection |
| Test coverage | 0% session tests | 100% session scenarios | `pytest tests/test_memory_session_integration.py` |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Session ID collision | Low | Medium | Use UUIDv4 or room name |
| Backward compatibility | Medium | Low | Existing memories will use fallback |
| Performance regression | Low | Low | Same query count, just proper scoping |
| ChromaDB migration needed | Low | High | Test schema compatibility first |

---

## Related Commits (for reference)

| Commit | Description |
|--------|-------------|
| `cfc6025` | Permanent fix: memory write in chat path + audit log |
| `646e735` | Fix memory recall: remove dead [Memory] merge block, increase retrieval k=4 |
| `74c3012` | Fix memory user_id tagging: store and retrieve with consistent user_id key |
| `f526408` | Fix memory user_id mismatch: write uses queued_user_id not runtime_user fallback |
| `94361fa` | Fix memory timing: await write before resolving queue future |

---

## Next Actions Checklist

- [ ] Phase A: Update `_store_chat_turn_memory` to accept and store session_id
- [ ] Phase A: Update call sites to pass session_id
- [ ] Phase A: Run unit tests
- [ ] Phase B: Add context-builder memory presence logging
- [ ] Phase B: Update SmartLLM audit metric
- [ ] Phase C: Add identity query pattern matching
- [ ] Phase C: Add explicit identity instruction for identity queries
- [ ] Phase D: Create integration test
- [ ] Phase D: Run three-turn live validation
- [ ] Phase D: Verify success criteria met
- [ ] Phase D: Tag v0.11.0 if all tests pass

---

## Appendix: Memory Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         MEMORY STORAGE FLOW                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   AgentOrchestrator                      HybridMemoryManager              │
│   ┌─────────────────┐                    ┌──────────────────────┐       │
│   │ .memory         │─────────────────▶│ store_conversation_  │       │
│   │ (injected)      │                    │ turn(user_msg,      │       │
│   └─────────────────┘                    │ assistant_msg, ...) │       │
│                                          │ [NEEDS session_id]  │       │
│                                          └──────────┬─────────┘       │
│                                                     │                    │
│                                          ┌──────────▼──────────┐       │
│                                          │  HybridRetriever    │       │
│                                          │  .add_memory()      │       │
│                                          └──────────┬──────────┘       │
│                                                     │                    │
│                               ┌─────────────────────┼─────┐              │
│                               ▼                     ▼     │              │
│                    ┌──────────────┐        ┌──────────────┐│            │
│                    │ VectorStore  │        │ KeywordStore ││            │
│                    │ (ChromaDB)   │        │ (SQLite FTS5)││            │
│                    └──────────────┘        └──────────────┘│            │
│                                                            │            │
└────────────────────────────────────────────────────────────┼────────────┘
                                                             │
┌────────────────────────────────────────────────────────────┼────────────┐
│                      MEMORY RETRIEVAL FLOW                 │            │
├────────────────────────────────────────────────────────────┼────────────┤
│                                                            ▼            │
│   SmartLLM                 ContextBuilder              HybridMemoryManager  │
│   ┌─────────────┐         ┌──────────────┐            ┌────────────────┐│
│   │ context_    │────────▶│ __call__()   │───────────▶│ get_user_      ││
│   │ builder     │         │              │            │ context(user_id)││
│   └─────────────┘         └──────────────┘            └────────────────┘│
│                                  │                           │          │
│                                  │                    ┌──────┴──────┐   │
│                                  │                    ▼             ▼   │
│                                  │           ┌───────────┐  ┌──────────┐ │
│                                  │           │ retrieve_ │  │ Hybrid   │ │
│                                  │           │ _relevant_│  │Retriever │ │
│                                  │           │ memories  │  │.retrieve │ │
│                                  │           │ [session_ │  │          │ │
│                                  │           │ id scope] │  │          │ │
│                                  │           └───────────┘  └──────────┘ │
│                                  │                                       │
│                                  │           ┌─────────────────────┐      │
│                                  └──────────│ memories injected   │      │
│                                              │ into system_content │      │
│                                              │ under ## Retrieved   │      │
│                                              │ Memories section    │      │
│                                              └─────────────────────┘      │
│                                                                           │
│   [CURRENT: Audit counts messages with "[Memory]" - always 0]            │
│   [FIXED: Audit detects "## Retrieved Memories" in system content]     │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## Conclusion

The memory pipeline's structural gaps have been identified through log analysis and code review. The fixes are straightforward and follow the existing patterns in the codebase. The most critical fix is ensuring `session_id` is stored in memory metadata, which will enable proper session-scoped retrieval. The audit metric fix will provide accurate observability into whether memories are reaching the LLM context.

**Estimated effort:** 2-3 hours of implementation + 1 hour of testing
**Risk level:** Low (additive changes, backward compatible)
**Blockers:** None
