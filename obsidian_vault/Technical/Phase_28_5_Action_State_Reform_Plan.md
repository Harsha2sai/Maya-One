# Phase 28.5: Action State Reform Plan

**Date:** April 8, 2026  
**Status:** Design Complete - Ready for Implementation  
**Priority:** CRITICAL - Blocks Multi-Turn Tool Use  
**Related:** Phase 28 (YouTube Fix), P23 (Delegation), Multi-Agent Architecture

---

## Executive Summary

This plan addresses the **"Agentic Chasm"** in Maya's multi-turn tool use - the gap between single-turn tool execution proficiency and conversational state management. Recent failures ("also Instagram", "close them", false "Opened" confirmations) are symptoms of architectural fragmentation, not parsing bugs.

**Key Insight from Research:** Even top LLMs (GPT-4, Claude 3.5) score only **~12%** on agentic memory tasks in BFCL v4 benchmarks. This is an architecture problem requiring explicit state management, not better prompting.

---

## Problem Statement

### Current Symptoms

| Symptom | Example | Root Cause |
|---------|---------|------------|
| Follow-up action fails | "open YouTube" → "also Instagram" | No action-state carryover |
| Anaphora unresolved | "close them" after opening apps | `PronounRewriter` only handles research |
| False confirmations | "Opened Chrome" (didn't launch) | No post-execution verification |
| Platform search fails | "videos about it" → pronoun only | Platform search handles pronouns, app actions don't |
| Unification failure | "I couldn't determine safe action" | Three independent routing paths |

### Root Cause Analysis

#### 1. Architecture Split: Three Overlapping Action Paths

```
User Input
    │
    ├──► FastPathRouter (deterministic regex, line 98-304)
    │       └── DirectToolIntent ──► immediate execution
    │
    ├──► AgentRouter (pattern + LLM, line 229-351)
    │       └── "system" route ──► SystemPlanner
    │
    └──► SystemPlanner (regex parser, line 144-362)
            └── SystemAction ──► controller execution
```

**Problem:** Each path parses independently with **no shared schema** - action context cannot carry between paths.

#### 2. Weak Action State Persistence

Current state (`fast_path_router.py:238-239`):
```python
self._turn_state["last_search_target"] = "youtube"
self._turn_state["last_search_query"] = query
```

**Problems:**
- Per-turn only, not conversation-scoped
- Only tracks search queries, not action objects (apps, files)
- No action sequence history for anaphora resolution
- `PronounRewriter` only handles research, not action objects

#### 3. Fragile Tool Returns

Current pattern (`pc_control.py:594`):
```python
return f"Successfully opened {app_name}"
```

**Problems:**
- Free-form strings, not structured receipts
- Success inferred from text, not actual system state
- No evidence captured for verification
- No error codes for recovery

#### 4. No Post-Execution Verification

```
Current:  Action Intent → Execute Tool → Return String
Missing:                (No Verification!)
```

---

## Research Foundation

### BFCL v4 Findings (Berkeley, 2025)

The Berkeley Function Calling Leaderboard v4 (July 2025) identified failure patterns matching your issues:

| BFCL Failure Mode | Your Symptom | Production Model Rate |
|-------------------|--------------|----------------------|
| Premature action before clarification | "open videos about it" | ~18% miss_param scenarios |
| Context dilution | Previous actions lost | ~23% long_context |
| State management failures | No persistent action objects | ~34% agentic memory |
| Agentic memory | Multi-turn state tracking | **~12%** even for top models |

**Source:** https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html

### ReAct v2 Timeline-Native Architecture (KDCube, 2025)

Modern production agents use structured timeline blocks:

**Key Innovation:** `Contribute` (persistent, shapes future turns) vs `Announce` (ephemeral, status only).

Your `turn_state` is close but needs to become conversation-scoped with typed action blocks.

**Source:** https://kdcube.tech/ReactV2.html

### Toolformer Filtering (Meta, 2023)

Toolformer used perplexity-based filtering to determine which API calls actually helped. Your system needs equivalent: **did this action actually produce the intended state change?**

**Source:** https://dl.acm.org/doi/10.5555/3666122.3669119

### CQR / AdaQR - Query Rewriting (ACL 2024)

Contextual Query Rewriting resolves anaphora like "close them" by linking to conversation action history.

**Sources:**
- Amazon CQR: https://www.amazon.science/publications/contextual-query-rewriting-for-spoken-dialogue-systems
- AdaQR: https://aclanthology.org/2024.emnlp-main.746/
- CREAD: https://aclanthology.org/2025.findings-acl.130/

### Rasa Forms & Home Assistant

Production assistants rely on conversation IDs + slot/state carryover for multi-turn coherence.

**Sources:**
- Rasa Forms: https://rasa.com/docs/rasa/forms
- Home Assistant Conversation API: https://www.home-assistant.io/integrations/conversation/

---

## Solution Architecture

### 1. Unified ActionIntent Schema

One canonical schema used by ALL routes:

```python
@dataclass
class ActionIntent:
    """Canonical action intent for all routing paths"""
    intent_id: str                    # Unique identifier
    target: Literal["web", "app", "terminal", "file", "system"]
    operation: Literal["open", "close", "search", "run", "write", "read", "kill"]
    entity: str                       # "youtube", "chrome", "downloads"
    query: Optional[str]              # search query, file content
    confidence: float                 # 0.0-1.0
    requires_confirmation: bool
    source_route: str                 # "fast_path", "system_planner", "agent_router"
    created_at: datetime

@dataclass
class ToolReceipt:
    """Structured tool execution result"""
    intent_id: str                    # Links to ActionIntent
    success: bool
    executed: bool                    # Did we actually run it?
    target: str
    evidence: Dict[str, Any]          # process_id, window_id, screenshot_hash
    error_code: Optional[str]         # "PROCESS_NOT_FOUND", "PERMISSION_DENIED"
    stdout: Optional[str]
    stderr: Optional[str]
    duration_ms: int
    timestamp: datetime

@dataclass
class VerificationResult:
    """Post-execution verification"""
    intent_id: str
    claimed_action: ActionIntent
    pre_state: SystemStateSnapshot
    post_state: SystemStateSnapshot
    verified: bool
    confidence: float
    method: Literal["process_check", "window_check", "screenshot_diff", "file_check"]
    message: str
```

### 2. Conversation Action State (ActionState)

Persistent action state for conversation-scoped references:

```python
@dataclass
class ActionState:
    """Persistent action state for anaphora resolution"""
    session_id: str
    opened_apps: List[AppReference]         # For "close them"
    closed_apps: List[AppReference]           # For "reopen that"
    last_search: Optional[SearchReference]  # For "search more"
    active_files: List[FileReference]       # For "delete that file"
    action_history: List[ActionIntent]      # Full sequence
    
    def resolve_anaphora(self, phrase: str) -> Optional[ResolvedReference]:
        """
        Resolve "them", "it", "that", "those" to action objects.
        
        Examples:
        - "close them" → last opened_apps (plural marker)
        - "open it" → last file in active_files
        - "search that" → last_search
        - "do that again" → most recent action
        """
        pass
    
    def add_action(self, intent: ActionIntent, receipt: ToolReceipt):
        """Add completed action to history with salience scoring"""
        pass
```

### 3. Structured Tool Receipts

Convert all tools to return structured receipts:

```python
# BEFORE (fragile):
# pc_control.py:594
return f"Successfully opened {app_name}"

# AFTER (verifiable):
# pc_control.py
return ToolReceipt(
    intent_id=intent_id,
    success=True,
    executed=True,
    target=app_name,
    evidence={
        "process_id": pid,
        "process_name": process_name,
        "window_id": wid,
        "desktop_file": desktop_file,
        "wm_class": wm_class
    },
    error_code=None,
    stdout=None,
    stderr=None,
    duration_ms=elapsed_ms,
    timestamp=datetime.now()
)
```

### 4. Post-Execution Verification Layer

Add verification before claiming success:

```python
async def execute_with_verification(
    intent: ActionIntent,
    executor: Callable
) -> VerifiedResult:
    """
    Execute tool with pre/post state verification.
    """
    # Capture pre-state
    pre_state = await capture_system_state(intent.target)
    
    # Execute
    receipt = await executor(intent)
    
    # Wait for state propagation
    await asyncio.sleep(0.5)
    
    # Capture post-state
    post_state = await capture_system_state(intent.target)
    
    # Verify
    verification = verify_state_change(pre_state, post_state, intent)
    
    if not verification.verified:
        return VerifiedResult(
            success=False,
            verified=False,
            message="I sent the command, but couldn't verify it worked. Please confirm.",
            evidence=receipt.evidence
        )
    
    return VerifiedResult(success=True, verified=True, ...)
```

### 5. Truthfulness Policy

Graduated responses based on verification:

| Verification State | Response Style | Example |
|-------------------|----------------|---------|
| Fully verified | Definitive | "Opened Chrome." |
| Sent but unverified | Hedged | "I sent the command to open Chrome. Please confirm it appeared." |
| Failed | Honest failure | "I tried to open Chrome but it didn't launch. Should I try again?" |
| Ambiguous intent | Clarification | "Should I open YouTube in the browser or the app?" |

---

## Implementation Phases

### Phase 28.5.1: Core Schema & Tool Receipts
**Duration:** 3-4 days  
**Risk:** Low (additive only)

**Tasks:**
1. [ ] Create `core/action/models.py` with `ActionIntent`, `ToolReceipt`, `VerificationResult`
2. [ ] Create `core/action/action_state.py` with `ActionState` class
3. [ ] Refactor `tools/system/pc_control.py`:
   - [ ] `open_app()` returns `ToolReceipt` with process/window evidence
   - [ ] `close_app()` returns `ToolReceipt` with verification
   - [ ] Add `verify_app_state(app_name)` utility
4. [ ] Create tests in `tests/test_action_models.py`

**Success Criteria:**
- All tool returns use structured receipts
- Tests verify receipt schema compliance
- No regression in existing functionality

### Phase 28.5.2: Conversation Action State
**Duration:** 4-5 days  
**Risk:** Medium (requires context integration)

**Tasks:**
1. [ ] Extend context system with `ActionState`:
   - [ ] Add to `ChatContext` or create `ActionStateManager`
   - [ ] Conversation-scoped persistence (not per-turn)
2. [ ] Update `PronounRewriter` for action anaphora:
   - [ ] Handle "close them" → resolve to opened apps
   - [ ] Handle "open it again" → resolve to closed apps
   - [ ] Handle "do that" → resolve to last action
3. [ ] Update `FastPathRouter`:
   - [ ] Query `ActionState` for anaphora resolution
   - [ ] Add action objects to state on execution
4. [ ] Create `tests/test_action_state.py`

**Success Criteria:**
- "close them" resolves to previously opened apps
- "also Instagram" recognizes prior "open" action context
- Anaphora resolution >90% accuracy on test set

### Phase 28.5.3: Verification Layer
**Duration:** 4-5 days  
**Risk:** Medium (timing-sensitive)

**Tasks:**
1. [ ] Create `core/system/verification_layer.py`:
   - [ ] `SystemStateSnapshot` capture utility
   - [ ] `verify_state_change()` with process/window checks
   - [ ] `capture_system_state()` for app/file/terminal states
2. [ ] Integrate into `SystemPlanner`:
   - [ ] Add verification step to `_route_to_controller()`
   - [ ] Update response templates with truthfulness policy
3. [ ] Create `tests/test_verification.py`:
   - [ ] Test false success detection
   - [ ] Test state change verification
   - [ ] Test timing edge cases

**Success Criteria:**
- False "Opened" confirmations reduced to <5%
- Verification correctly identifies failed launches
- No significant latency increase (>200ms acceptable)

### Phase 28.5.4: Unified Routing
**Duration:** 5-7 days  
**Risk:** High (changes core routing)

**Tasks:**
1. [ ] Create `core/routing/unified_router.py`:
   - [ ] Unified intent classification outputting `ActionIntent`
   - [ ] Merge `FastPathRouter` patterns with `SystemPlanner` actions
   - [ ] Single entry point for all tool intents
2. [ ] Refactor existing routers:
   - [ ] `FastPathRouter` outputs `ActionIntent` (backward compat)
   - [ ] `SystemPlanner` outputs `ActionIntent` (backward compat)
   - [ ] `AgentRouter` delegates to unified router for system intents
3. [ ] Add feature flag `UNIFIED_ROUTING=1` for gradual rollout
4. [ ] Create `tests/test_unified_routing.py`

**Success Criteria:**
- All routes produce `ActionIntent` objects
- Unified routing passes all existing tests
- Feature flag allows safe rollback

### Phase 28.5.5: Regression Tests & Integration
**Duration:** 3-4 days  
**Risk:** Low (testing only)

**Tasks:**
1. [ ] Create multi-turn test suite:
   - [ ] App open/close sequences with anaphora
   - [ ] Truthfulness verification (false success detection)
   - [ ] Structured receipt validation
   - [ ] Action state carryover across conversation turns
2. [ ] Create `tests/test_transcript_regression.py`:
   - [ ] YouTube → Instagram follow-up
   - [ ] "close them" after opening multiple apps
   - [ ] "open videos about it" with prior subject
3. [ ] Performance benchmarks:
   - [ ] Latency impact of verification
   - [ ] Memory usage of ActionState

**Success Criteria:**
- All existing tests pass
- New multi-turn tests pass
- Performance within 10% of baseline

---

## File Changes Summary

### New Files
```
Agent/core/action/
├── __init__.py
├── models.py                 # ActionIntent, ToolReceipt, VerificationResult
├── action_state.py           # ActionState with anaphora resolution
└── constants.py              # Enums and constants

Agent/core/system/
├── verification_layer.py     # State capture and verification

Agent/tests/
├── test_action_models.py
├── test_action_state.py
├── test_verification.py
└── test_unified_routing.py
```

### Modified Files
```
Agent/tools/system/pc_control.py      # Structured receipts
Agent/core/orchestrator/
├── fast_path_router.py               # ActionState integration
├── agent_router.py                   # Unified routing
├── pronoun_rewriter.py               # Action anaphora
└── system/
    └── system_planner.py             # Verification layer
```

---

## Success Metrics

| Metric | Current | Phase 28.5 Target | Measurement |
|--------|---------|-------------------|-------------|
| "also X" follow-up success | ~30% | >90% | Test suite |
| Anaphora resolution | ~20% | >85% | Test suite |
| False "Opened/Closed" confirmations | Unknown | <5% | Verification tests |
| Structured receipt coverage | 0% | 100% (app/close) | Code review |
| Tool verification coverage | 0% | 100% (app/close) | Code review |
| Truthfulness (verified claims) | ~60% | >95% | Manual audit |

---

## Dependencies

### Blocks (Must Complete First)
- [x] Phase 28 (YouTube platform search) - baseline established

### Parallel Work (Can Proceed Concurrently)
- [ ] P23 Plan (Delegation) - complementary, not blocking
- [ ] Multi-Agent Architecture - benefits from this foundation

### Blocked By This (Must Wait)
- [ ] Multi-agent handoffs with action context
- [ ] Background task action continuity
- [ ] Team mode action state sharing

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Verification timing issues | Medium | Medium | Configurable delays, async polling |
| Backward compatibility breaks | Medium | High | Feature flags, gradual rollout |
| Performance regression | Low | Medium | Benchmarks, caching |
| Anaphora resolution ambiguity | High | Low | Clarification prompts |
| Schema evolution drift | Medium | Medium | Versioned contracts + adapter compatibility tests |
| State persistence mismatch | Medium | High | Define persistence boundary (session-only vs durable), TTL cleanup, migration notes |
| Privacy leakage in action receipts | Low | High | Redact sensitive fields before persistence/telemetry, minimize raw payload retention |
| Scope creep | Medium | Medium | Strict phase gates |

---

## Appendix A: Research Sources

1. **ReAct: Synergizing Reasoning and Acting** (Yao et al., 2023)
   - https://arxiv.org/abs/2210.03629

2. **Toolformer: Language Models Can Teach Themselves to Use Tools** (Schick et al., NeurIPS 2023)
   - https://dl.acm.org/doi/10.5555/3666122.3669119

3. **BFCL v4: Berkeley Function Calling Leaderboard** (2025)
   - https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html

4. **API-Bank: Comprehensive Benchmark for Tool-Augmented LLMs** (Li et al., EMNLP 2023)
   - https://aclanthology.org/2023.emnlp-main.187

5. **KDCube ReAct v2: Timeline-Native Architecture** (2025)
   - https://kdcube.tech/ReactV2.html

6. **Contextual Query Rewriting for Spoken Dialogue Systems** (Amazon, 2020)
   - https://www.amazon.science/publications/contextual-query-rewriting-for-spoken-dialogue-systems

7. **AdaQR: Adaptive Query Rewriting for Conversational Search** (ACL 2024)
   - https://aclanthology.org/2024.emnlp-main.746/

8. **CREAD: Conversational Response Re-ranking** (ACL Findings 2025)
   - https://aclanthology.org/2025.findings-acl.130/

9. **Rasa Forms Documentation**
   - https://rasa.com/docs/rasa/forms

10. **Home Assistant Conversation API**
    - https://www.home-assistant.io/integrations/conversation/

11. **Open Interpreter Safe Mode**
    - https://docs.openinterpreter.com/safety/safe-mode

12. **Semantic Kernel Planning** (Microsoft)
    - https://learn.microsoft.com/en-us/semantic-kernel/concepts/planning

---

## Appendix B: Current Code References

### FastPathRouter (3 action paths)
- File: `Agent/core/orchestrator/fast_path_router.py`
- Lines: 98-304 (`detect_direct_tool_intent`)
- State: Lines 238-239 (per-turn only)

### SystemPlanner (independent parsing)
- File: `Agent/core/system/system_planner.py`
- Lines: 144-362 (`_parse_intent`)
- Fallback: Line 48 ("couldn't determine...")

### Tool Returns (free-form strings)
- File: `Agent/tools/system/pc_control.py`
- Open: Line 594
- Close: Line 695

### PronounRewriter (research-only)
- File: `Agent/core/orchestrator/pronoun_rewriter.py`
- Scope: Research context only
- Missing: Action object resolution

---

**Next Steps:** See today's daily note for immediate action items.
