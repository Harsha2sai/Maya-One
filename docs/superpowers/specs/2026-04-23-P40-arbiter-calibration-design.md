# Phase 40.0.1 — Arbiter Calibration Patch Design

## Why Scoring Fixes Won't Hold

Before diving into the plan, the key finding: **the failure modes are pipeline interaction problems, not single failure points**.

Typical regressions surface as stacked leakages:

1. **Explicit intent preempts scoring** — `_classify_explicit_intent` short-circuits, skipping context evaluation
2. **Scoring is context-weak** — scoring functions treat state as a secondary signal, not primary
3. **Ambiguity gate fires on deterministic inputs** — the gate does its job correctly, but deterministic inputs should never reach it

> **Core architectural principle:** When certainty is structurally or contextually guaranteed, do not enter probabilistic resolution. The arbiter should only invoke scoring + ambiguity gating when no deterministic override applies.

---

## Pre-Work: Scoring Matrix Freeze

Before any code changes, enumerate **all 5 owners × all interactions × before/after scores** for every probe in the gate matrix (P1–P10). This documents exactly what changes and why. Do per-rule shadow logging (log decision from new rule, apply legacy decision) to catch regressions before stacking.

---

## Implementation Changes

### In `state_arbiter.py`

#### 1. Unified Deterministic Routing Layer (pre-scoring, before `_score_candidates()`)

Insert between explicit intent check and scoring. Both deterministic overrides clear `clarify_ctx` on return.

```python
# Pre-scoring overrides: return directly, bypass scoring + ambiguity gate
deterministic = self._check_reminder_followup_determinism(
    text=lowered,
    state=state,
)
if deterministic:
    return deterministic

deterministic = self._check_profile_statement_determinism(text=lowered)
if deterministic:
    return deterministic
```

#### 2. `reminder_followup_determinism()`

**Condition:** `reminder_hint` present AND (`has_last_action` OR `has_pending_scheduling`) AND text is NOT a new imperative scheduling command.

- Query forms to exclude from explicit `scheduling_command` intent:
  - "what reminder did I set"
  - "when is my reminder"
  - "what did I set"
  - "show reminders"
  - "list reminders"
  - "which reminder"
  - "when is it"
  - "what is it for"

**Implementation options (picked hybrid):**

- Option A (explicit intent surgical refinement): Add `is_query_form()` check in `_classify_explicit_intent` for scheduling patterns. Query forms return empty string intent, letting scoring decide.
- Option B (pre-scoring dominance override): Add `_check_reminder_followup_determinism()` that fires before scoring. If matched → return `action_followup` with confidence 0.95, reason="context_dominant".

**Picked:** Option B as primary fix, Option A as supporting refinement.

#### 3. `profile_self_statement_determinism()`

**Condition:** Matches a declarative profile self-statement AND NOT in programming context.

- Declarative patterns: "my name is X", "i am X", "call me X"
  - Must NOT contain interrogative markers (?, "do you", "what is", "tell me")
  - Must be simple attribute assignment (1-2 sentences max)

- Programming context patterns that short-circuit (syntax-level):
  - `def `, `class `, `import `, `fn `, `func `
  - `= ` followed by expression, `let `, `const `, `var `

- Programming context patterns that score-penalize (contextual):
  - "in python", "in javascript", "in java"
  - "function", "class", "variable", "code"
  - "write code", "code example", "syntax"

**Hybrid decision:** Syntax-level triggers deterministic override → return `general_chat` with confidence 0.90, reason="declarative_profile_update". Contextual triggers score penalty within scoring.

#### 4. Programming Context Negative Guard (Hybrid)

**Short-circuit (before scoring):**

```python
if re.search(r'\b(def |class |import |fn |func |let |const |var )', text):
    return ArbitrationDecision(owner="general_chat", confidence=0.92, ...)
```

**Score penalty (within `_score_candidates`):**

```python
if re.search(r'\b(python|javascript|java|function|class|variable|code)\b', text):
    scores["entity_followup"] = min(scores.get("entity_followup", 0), 0.15)
    scores["action_followup"] = min(scores.get("action_followup", 0), 0.15)
    scores["profile_recall"] = min(scores.get("profile_recall", 0), 0.15)
    scores["general_chat"] = max(scores.get("general_chat", 0), 0.80)
```

#### 5. Clarify Threshold Tightening

**Keep** `_min_confidence = 0.60`. Lower `_ambiguity_delta` from 0.15 to 0.10 (narrower gap makes it harder for cross-domain pairs to trigger ambiguity).

**Tighten the condition** by adding "both are strong" gate alongside the ambiguity check:

```python
if (ambiguous or winner_score < self._min_confidence):
    # Only clarify if ambiguity threshold met AND BOTH candidates are "strong" (≥0.45)
    both_strong = winner_score >= 0.45 and second_score >= 0.45
    if ambiguous and both_strong:
        # Trigger clarify — both cross-domain candidates are close AND strong
        ...
    else:
        # Pick winner — bypass clarify
        decision = ArbitrationDecision(owner=winner_owner, confidence=winner_score, ...)
        return decision
```

This means:
- Clear winner (conf ≥ 0.60) → pick winner
- Low confidence (conf < 0.60) but not ambiguous (gap ≥ 0.10) → pick winner
- Low confidence and ambiguous but one or both candidates weak (<0.45) → pick winner
- Ambiguous (gap < 0.10) AND both strong (≥0.45) → clarify

#### 6. Clarify Context Reuse Tightening

**Only apply `clarify_ctx` bias** (the 0.20–0.25 bonus) when:
- Current turn is a terse disambiguation turn: pronoun-only, short reminder-only, direct follow-up fragment (word count ≤ 8)
- AND prior clarify context exists from the previous turn

**Clear `clarify_ctx`** on any explicit research start or profile self-statement:

```python
if explicit_research_start_detected(text) or profile_self_statement_detected(text):
    self._clear_clarify_context(session_key)
```

#### 7. First-Turn Research Detection

**Condition:** Text matches research-entry pattern AND first turn (turn_index ≤ 1) AND NOT programming context AND NOT profile/self-reference.

- Research-entry patterns: "tell me about X", "who is X", "what is X", "do you know about X"
  - Must exclude: "my name", "your name", "about yourself"

**Effect:** These select the existing entity/research path. Scores must reflect "first-turn research is not ambiguous."

- `entity_followup`: base only from pronoun + valid active entity OR explicit research-entry pattern with no prior state. Do NOT let `recent_research` alone create a first-turn winner.
- `general_chat`: safe fallback, but should not win over clear research signals.

#### 8. Drift Handling

**Condition:** If active entity was sanitized as "drifted" or "expired" in `_clean_state`, do NOT let pronoun alone (`him`, `it`) elevate `entity_followup` into a winner.

Implementation: In `_score_candidates`, if `state["active_entity"]` was populated but the sanitization reason was `drifted_context`, cap `entity_followup` at 0.40.

#### 9. Multi-Entity Ambiguity Guard

**Condition:** If current or immediately previous research request contains multiple entities ("X and Y", "both X and Y") or conjunction markers, and current text is a later pronoun follow-up, return `clarify`.

Implementation: Detect multi-entity research (patterns: ` \bAND\b`, `, and `, `both `, `both X and Y`) and maintain a one-turn multi-entity flag. On pronoun follow-up with flag set → return `clarify`.

#### 10. Multi-Signal Test: Drift + Multi-Entity Combined

For probes like "what about it" after a drifted entity with prior multi-entity research:

- Drift guard suppresses `entity_followup` to ≤ 0.40
- Multi-entity flag triggers clarify
- Result: `clarify` (correct)

---

### Extended Logging

Add to all `state_arbiter_decision` log lines:

```python
"winner_margin=%.3f runner_up=%s"
% (winner_score - second_score, second_owner)
```

For derive-gate validation: log `false_clarify_count` per probe in summary.

---

### Scope Boundaries

**Included:**
- All changes to `state_arbiter.py`
- Preserve existing `chat_mixin.py` single seam
- First-turn research reuses existing entity/research path (no new route family)
- Existing Phase 39 state semantics unchanged: single active entity, single last action, minimal pending scheduling carryover

**Excluded:**
- No new public owner type
- No router or planner redesign
- No database or backend changes

---

## Test Changes

### In `test_state_arbiter.py` — unit coverage

| Scenario | Current state | Expected after |
|----------|--------------|----------------|
| `"tell me about Elon Musk"` first turn | likely `clarify` | `entity_followup` / `general_chat` |
| `"what reminder did I set"` with valid last_action | likely `scheduling_command` | `action_followup` |
| `"what is my name in python"` | likely `clarify` | `general_chat` |
| `"my name is Harsha"` | likely `clarify` | `general_chat` (declarative bypass) |
| `"tell me about X → what about it"` after drifted entity | unknown | `clarify` (drift guard) |
| `"what about him"` after multi-entity research | unknown | `clarify` (multi-entity guard) |
| `"tell me about X" → "tell me about Y"` | unknown | second does NOT pick up X's entity |

Additional:
- Profile self-statement after clarify turn does not inherit clarify context
- Programming syntax patterns short-circuit to `general_chat` before scoring
- First-turn research with programming context goes to `general_chat`

### In `test_agent_orchestrator.py` — seam-level checks

| Probe sequence | Validation |
|---------------|------------|
| `"tell me about Elon Musk"` after prior clarify | Does NOT trigger clarify loop fallback |
| `"what reminder did I set"` | Resolves through action_followup, not scheduling_command |
| `"what is my name in python"` | Bypasses profile_recall → `general_chat` |
| `"my name is Harsha → tell me about Elon Musk → what is my name → tell me more about him"` | Profile / entity separation preserved |

---

## Gate Validation / False Clarify Detection

### Instrument A: Test Assertions

In test runner, for deterministic-signal probes, assert:

```python
assert decision.owner != "clarify", f"false_clarify on: {message}"
```

### Instrument B: Code + Forced Intent Parameter

In `_build_clarify_or_fallback`, add `forced_intent` parameter. When called from deterministic override, pass `forced_intent="action_followup"` or `"general_chat"`. If `forced_intent` was set and `clarify` fires → log `false_clarify_deterministic`.

### Instrument C: Post-Hoc Gate Log Analysis

Parse existing `state_arbiter_decision` log lines:

```bash
grep "state_arbiter_decision owner=clarify" /tmp/p40_gate_v4/*.log
```

If `owner=clarify` AND message matches a deterministic-signal pattern (reminder follow-up with valid state, first-turn research, profile self-statement) → increment `false_clarify_count`.

### Derived Gate Assertions

```
false_clarify_count = 0  # across the full matrix
```

Definition: Arbiter chose `clarify` when a valid research-entry, action-followup, or profile self-reference signal was present.

### Latency Interpretation

- Arbiter decision latency (measured within `state_arbiter_decision`) should stay low
- Process cold-start latency is NOT used as arbiter-only blocker unless warm-path latency also regresses
- Cold-start failures in the gate matrix likely indicate upstream bottlenecks, not arbiter bugs

---

## Phased Rollout

1. **Phase 1:** Add deterministic routing layer with both `reminder_followup_determinism` and `profile_self_statement_determinism`. Run unit tests + targeted arbiter tests.
2. **Phase 2:** Add programming context hybrid guard + first-turn research detection. Run full arbiter test suite.
3. **Phase 3:** Add clarify threshold tightening + clarify context reuse hygiene. Run existing Phase 40 test suite.
4. **Phase 4:** Add drift handling + multi-entity ambiguity guard. Run shadow gate validation.
5. **Phase 5:** Extended logging + instrument B code. Run gate log analysis (instrument C).
6. **Phase 6:** Full gate re-run with all assertions.

---

## Key Design Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Explicit scheduling intent | Add query-vs-imperative discrimination | Don't remove, refine — queries pass through to scoring |
| Reminder follow-up routing | Pre-scoring dominance override | Context should override text when state is strong |
| Profile self-statement routing | Pre-scoring deterministic override | Declarative statements are state mutations, not intents to classify |
| Programming context guard | Hybrid (short-circuit + score penalty) | Syntax patterns vs contextual mentions need different handling |
| Clarify threshold | Reduce delta to 0.10, keep 0.60 min_conf, add "both strong" gate | Narrower gap makes it harder to trigger ambiguity; both-strong guard prevents clarifying on weak candidates |
| False clarify detection | All three instruments | Tests catch regressions, code adds assertions, logs enable post-hoc validation |
| First-turn research | Reuse existing entity/research path | No new route family, minimal blast radius |
| Drift handling | Cap entity_followup at 0.40 on drifted state | Prevents stale pronoun reference from winning |
| Multi-entity guard | One-turn flag + pronoun → clarify | Conjunction markers block ambiguous pronoun resolution |

---

## Files Touched

| File | Change type |
|------|-------------|
| `Agent/core/orchestrator/state_arbiter.py` | Implementation (new deterministic layer, hybrid guard, threshold tightening, drift/multi-entity handling) |
| `Agent/core/orchestrator/chat_mixin.py` | No code changes (preserve single seam, add logging if needed) |
| `Agent/tests/test_state_arbiter.py` | New unit tests per scenario table |
| `Agent/tests/test_agent_orchestrator.py` | New seam-level tests per sequence table |
| `docs/superpowers/specs/2026-04-23-P40-arbiter-calibration-design.md` | This document |

---

## Assumptions (carryforward from Phase 40.0.1 plan)

- No new public owner type is introduced
- No router or planner redesign
- Existing Phase 39 state semantics unchanged: single active entity, single last action, minimal pending scheduling carryover
- Staged Phase 40 scope (ChatMixin, StateArbiter, RuntimeMetrics, tests) remains the implementation boundary