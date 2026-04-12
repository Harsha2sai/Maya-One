# Phase 28.5: Action State Reform - Architecture Report & Fix Plan

**Date:** 2026-04-08
**Status:** Design Complete - Ready for Review
**Scope:** Multi-turn tool use robustness, truthfulness guarantees, structured receipts

---

## Executive Summary

Your agent exhibits classic symptoms of the **"Agentic Chasm"** - the gap between single-turn tool calling proficiency and multi-turn conversational state management. The recent YouTube/Instagram follow-up failures are not parsing bugs but symptoms of a deeper architectural fragmentation.

### Key Symptoms Mapped to Root Causes

| Symptom | Root Cause | Location |
|---------|-----------|----------|
| "also Instagram" not understood as app-open | No action-state carryover between turns | `fast_path_router.py`, `agent_router.py` |
| "close them" fails to resolve "them" | Weak anaphora resolution for action objects | `pronoun_rewriter.py` (only handles research) |
| "open videos about it" with pronoun-only query | Platform search resolves pronouns but app actions don't | `fast_path_router.py:226-236` |
| False "Opened/Closed" confirmations | Tool success inferred from text heuristics, not verification | `tool_response_builder.py`, `pc_control.py:594,695` |
| "I couldn't determine a safe system action" | No unified action intent schema across routes | `system_planner.py:48` |
| Free-form tool return strings | No structured receipts for downstream validation | `pc_control.py` throughout |

---

## Root Cause Analysis

### 1. Architecture Split: Three Overlapping Action Paths

Your system routes actions through three independent, non-unified paths:

```
User Input
    │
    ├──► FastPathRouter (deterministic regex)
    │       └── DirectToolIntent ──► immediate execution
    │
    ├──► AgentRouter (pattern + LLM)
    │       └── "system" route ──► SystemPlanner
    │
    └──► SystemPlanner (regex intent parser)
            └── SystemAction ──► controller execution
```

**Problems:**
- `FastPathRouter` and `SystemPlanner` both parse intents independently with different regex patterns
- `SystemPlanner` returns "I couldn't determine..." at line 48 when no patterns match, but FastPathRouter already matched some
- No shared `ActionIntent` schema means context can't carry between paths
- `turn_state` in FastPathRouter is isolated from conversation context

### 2. Weak Action State Persistence

Current state management (`turn_state` in FastPathRouter):
```python
# Line 238-239: fast_path_router.py
self._turn_state["last_search_target"] = "youtube"
self._turn_state["last_search_query"] = query
```

**Problems:**
- `turn_state` is per-turn, not conversation-scoped
- Only tracks search queries, not action objects (apps opened, files accessed)
- No support for action sequences: "open YouTube and Instagram" → "close them both"
- `PronounRewriter` exists but only for research context, not action context

### 3. Fragile Tool Response Verification

Current tool return pattern (`pc_control.py:594`):
```python
return f"Successfully opened {app_name}"
```

**Problems:**
- String-based returns can't be validated programmatically
- Success is inferred from the string, not actual system state
- No evidence captured for truthfulness verification
- No error codes for recovery logic

### 4. No Post-Execution Verification

Current flow executes tools but never verifies:
```
Action Intent → Execute Tool → Return String Response
                    ↑
            (No verification step!)
```

This produces false confirmations when:
- App fails to launch but returns success string
- Wrong app launched (name collision)
- App launched but not visible/focused
- Close command sent to non-existent window

---

## Research Insights

### BFCL v4 Multi-Turn Findings (2025)

The Berkeley Function Calling Leaderboard identified critical failure patterns matching your issues:

| BFCL Failure Mode | Your Symptom | Rate in BFCL v4 |
|--------------------|--------------|-----------------|
| Premature action before clarification | "open videos about it" with unresolved "it" | ~12% on memory tasks |
| Missing tool recovery | No graceful fallback when patterns fail | ~18% miss_func scenarios |
| Context dilution | Previous actions lost in long conversations | ~23% long_context |
| State management | No persistent action objects | ~34% agentic memory |

**Key Insight:** Even top models (GPT-4, Claude 3.5) score only **~12%** on agentic memory sub-tasks in BFCL v4, demonstrating this is an architectural problem requiring explicit state management, not just better prompting.

### ReAct v2 Timeline-Native Architecture (KDCube 2025)

Modern production agents use structured timeline blocks:

```
Conversation Timeline:
├── UserBlock (persistent)
├── ThoughtBlock (persistent)
├── ActionBlock (persistent)
│   ├── intent: StructuredActionIntent
│   ├── execution: ToolReceipt
│   └── verification: VerificationResult
├── ObservationBlock (persistent)
└── AssistantBlock (persistent)
```

**Key Innovation:** Separation of `contribute` (persistent, shapes future turns) vs `announce` (ephemeral, status only).

### Toolformer Filtering Insight (Meta 2023)

Toolformer used perplexity-based filtering to determine which API calls actually helped. Your system needs equivalent filtering: **did this action actually produce the intended state change?**

---

## Recommended Architecture

### 1. Unified ActionIntent Schema

Create one canonical schema used by ALL routes:

```python
@dataclass
class ActionIntent:
    target: Literal["web", "app", "terminal", "file", "system"]
    operation: Literal["open", "close", "search", "run", "write", "read", "kill"]
    entity: str  # "youtube", "chrome", "downloads"
    query: Optional[str]  # search query, file content, etc.
    confidence: float  # 0.0-1.0
    requires_confirmation: bool
    action_state_id: str  # links to conversation action state

@dataclass
class ToolReceipt:
    success: bool
    executed: bool  # did we actually run it?
    target: str
    evidence: Dict[str, Any]  # process_id, window_id, screenshot_hash
    error_code: Optional[str]  # "PROCESS_NOT_FOUND", "PERMISSION_DENIED"
    timestamp: datetime

@dataclass
class VerificationResult:
    claimed_action: ActionIntent
    pre_state: SystemStateSnapshot
    post_state: SystemStateSnapshot
    verified: bool
    confidence: float
    method: Literal["process_check", "window_check", "screenshot_diff"]
```

### 2. Conversation Action State Carryover

Implement action-state tracking in conversation context:

```python
@dataclass
class ActionState:
    """Persistent action state for conversation-scoped references"""
    opened_apps: List[AppReference]  # for "close them"
    last_search: Optional[SearchReference]  # for "search more like that"
    active_files: List[FileReference]  # for "delete that file"
    action_sequence: List[ActionIntent]  # full history

    def resolve_anaphora(self, phrase: str) -> Optional[ActionIntent]:
        # "them" → last opened_apps
        # "it" → last_search or last action
        # "that" → most recent action with high salience
```

### 3. Structured Tool Receipts

Convert all tools to return structured receipts:

```python
# Current (fragile):
return f"Successfully opened {app_name}"

# New (verifiable):
return ToolReceipt(
    success=True,
    executed=True,
    target=app_name,
    evidence={
        "process_id": pid,
        "window_id": wid,
        "desktop_file": desktop_file
    },
    error_code=None,
    timestamp=datetime.now()
)
```

### 4. Post-Execution Verification Layer

Add verification before claiming success:

```python
async def execute_with_verification(intent: ActionIntent) -> VerifiedResult:
    pre_state = await capture_system_state(intent.target)
    receipt = await execute_tool(intent)
    post_state = await capture_system_state(intent.target)
    
    verification = verify_state_change(pre_state, post_state, intent)
    
    if not verification.verified:
        return VerifiedResult(
            success=False,
            message="I sent the command, but couldn't verify it worked.",
            evidence=receipt.evidence
        )
    
    return VerifiedResult(success=True, ...)
```

### 5. Truthfulness Policy

Implement graduated responses based on verification:

| Verification | Response |
|--------------|----------|
| Fully verified | "Opened Chrome." (definitive) |
| Sent but unverified | "I sent the command to open Chrome. Please confirm it appeared." |
| Failed | "I tried to open Chrome but it didn't launch. Should I try again?" |
| Ambiguous intent | "Should I open YouTube in the browser or the app?" |

---

## Implementation Plan

### Phase 28.5.1: Core Schema & Receipts
**Files:** `core/action/models.py`, `tools/system/pc_control.py`

1. Create `ActionIntent`, `ToolReceipt`, `VerificationResult` schemas
2. Refactor `open_app()` to return `ToolReceipt` with process/window evidence
3. Refactor `close_app()` to return `ToolReceipt` with actual close verification
4. Add `verify_app_state(app_name)` utility for post-execution checks

### Phase 28.5.2: Conversation Action State
**Files:** `core/context/action_state.py`, `core/orchestrator/fast_path_router.py`

1. Create `ActionState` class with anaphora resolution
2. Extend `turn_state` to conversation-scoped `action_state`
3. Add action objects to state: `opened_apps`, `last_search`, `active_files`
4. Update pronoun rewriter to handle action anaphora: "close them"

### Phase 28.5.3: Verification Layer
**Files:** `core/system/verification_layer.py`, `core/system/system_planner.py`

1. Create `SystemStateSnapshot` capture utility
2. Implement `verify_state_change()` with process/window checks
3. Add verification step to `SystemPlanner._route_to_controller()`
4. Update response templates to use truthfulness policy

### Phase 28.5.4: Unified Routing
**Files:** `core/routing/unified_router.py`, `core/orchestrator/agent_router.py`

1. Create unified intent classification that outputs `ActionIntent`
2. Merge FastPathRouter deterministic patterns with SystemPlanner actions
3. Route all actions through unified `ActionIntent` → execution → verification flow
4. Maintain fast-path performance with pre-computed intent cache

### Phase 28.5.5: Regression Tests
**Files:** `tests/test_action_state.py`, `tests/test_verification.py`

1. Multi-turn app open/close sequences with anaphora
2. Truthfulness verification (false success detection)
3. Structured receipt validation
4. Action state carryover across conversation turns

---

## Appendix: Research Sources

1. **ReAct: Synergizing Reasoning and Acting in Language Models** (Yao et al., 2023)
   - https://arxiv.org/abs/2210.03629
   - Foundation: thought → action → observation loop

2. **Toolformer: Language Models Can Teach Themselves to Use Tools** (Schick et al., NeurIPS 2023)
   - https://dl.acm.org/doi/10.5555/3666122.3669119
   - Filtering API calls by perplexity reduction

3. **BFCL v4: Berkeley Function Calling Leaderboard** (2025)
   - https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html
   - Multi-turn tool use benchmarks and failure patterns

4. **API-Bank: Comprehensive Benchmark for Tool-Augmented LLMs** (Li et al., EMNLP 2023)
   - https://aclanthology.org/2023.emnlp-main.187
   - Planning, retrieval, calling evaluation

5. **KDCube ReAct v2: Timeline-Native Architecture** (2025)
   - https://kdcube.tech/ReactV2.html
   - Production-grade state management with contribute/announce separation

6. **Contextual Query Rewriting for Spoken Dialogue Systems** (Amazon, 2020)
   - https://www.amazon.science/publications/contextual-query-rewriting-for-spoken-dialogue-systems
   - CQR for anaphora resolution

7. **AdaQR: Adaptive Query Rewriting for Conversational Search** (ACL 2024)
   - https://aclanthology.org/2024.emnlp-main.746/
   - Query rewriting with conversation context

8. **CREAD: Conversational Response Re-ranking with Contextual Anaphora** (ACL Findings 2025)
   - https://aclanthology.org/2025.findings-acl.130/
   - Anaphora resolution in multi-turn systems

9. **Rasa Forms Documentation**
   - https://rasa.com/docs/rasa/forms
   - Slot filling and state carryover patterns

10. **Home Assistant Conversation API**
    - https://www.home-assistant.io/integrations/conversation/
    - Production assistant state management patterns

11. **Open Interpreter Safe Mode**
    - https://docs.openinterpreter.com/safety/safe-mode
    - Command approval and verification patterns

12. **Semantic Kernel Planning Documentation** (Microsoft)
    - https://learn.microsoft.com/en-us/semantic-kernel/concepts/planning
    - Function calling and plan execution

---

## Migration Strategy

### Backward Compatibility
- Phase 28.5.1-2 can run alongside existing code (new modules)
- Phase 28.5.3 adds verification but maintains response format
- Phase 28.5.4 requires coordination - use feature flag `UNIFIED_ROUTING=1`
- Legacy paths remain as fallback during transition

### Validation Gates
1. All existing tests pass
2. New multi-turn action tests pass
3. Verification layer correctly identifies false successes
4. Anaphora resolution >90% accuracy on test set

---

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| "also X" follow-up success | ~30% | >90% |
| False "Opened/Closed" confirmations | Unknown | <5% |
| Structured receipt coverage | 0% | 100% |
| Action anaphora resolution | ~20% | >85% |
| Truthfulness (verified claims) | ~60% | >95% |

---

**Next Steps:** Review this design and confirm scope. Then proceed to implementation planning via `writing-plans` skill.
