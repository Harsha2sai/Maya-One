# P12-01 Voice Path Memory — Full Static Analysis
**Date:** 2026-03-31  
**Scope:** Pre-smoke validation of voice-path memory write and retrieval before live session testing

---

## Voice Turn Entry Point

```
_on_user_input_transcribed (agent.py:2008)
  └─> _dispatch_voice_after_grace (async)
        └─> _handle_text_chat_input(text, sender, participant, origin="voice")
              └─> tool_ctx = _build_tool_context(participant, turn_id, sender)
              └─> phase3_orchestrator.handle_message(text, user_id=f"livekit:{sender}", tool_ctx, origin="voice")
```

---

## Identity (user_id / session_id) Derivation — Voice Path

| Field | Derivation | Source |
|---|---|---|
| `sender` | `speaker_id` from transcription event, or participant `identity` fallback | `agent.py:2033` |
| `user_id` passed to orchestrator | `f"livekit:{sender}"` — always prefixed | `agent.py:1470` |
| `tool_ctx.user_id` | `metadata.get("user_id") or sender` — NO livekit: prefix | `agent.py:853` |
| `tool_ctx.session_id` | `trace_ctx.get("session_id")` = `room.name` | `agent.py:864` |
| `memory_session_id` (in Phase6 context builder path) | `tool_ctx.session_id or self._current_session_id or room.name or "console_session"` | `orchestrator:4146` |

> **Risk identified:** `user_id` passed to `handle_message` = `"livekit:{sender}"` but `tool_ctx.user_id` = raw metadata or sender with no prefix. These can diverge.

---

## Voice Memory READ Path

```
handle_message(origin="voice")
  └─> _handle_chat_response_core (via _handle_chat_response queue)
        └─> _phase6_context_builder_path()
              └─> context_builder.build_for_voice(
                    user_id=user_id,          # "livekit:{sender}"
                    session_id=memory_session_id,  # room.name
                    retriever=self.memory.retriever
                  )
                    └─> HybridRetriever.retrieve_with_scope_fallback(
                          query, user_id, session_id, origin="voice", k=VOICE_RETRIEVER_K=2
                        )
                          └─> retrieve_async (session-scoped first, fallback to user-only)
                                └─> HybridRetriever.retrieve(k, k_vector, k_keyword)
                                      └─> _voice_budget() caps k=min(2,3)=2, k_vector=min(10,4)=4, k_keyword=min(10,4)=4
```

**Also:** `_retrieve_memory_context_async` is called separately at the top of `handle_message` for `_should_skip_memory` guard path — uses `VOICE_MEMORY_MAX_RESULTS=2` and `VOICE_MEMORY_TIMEOUT_S=0.60s`.

---

## Voice Memory WRITE Path

```
_handle_chat_response (queue dispatch loop, orchestrator:3509-3540)
  └─> _handle_chat_response_core(queued_message, queued_user_id, origin=queued_origin)
        ← returns response
  └─> _store_chat_turn_memory(
          queued_message,
          response,
          user_id=queued_user_id,    # "livekit:{sender}"
          session_id=queued_session_id   # tool_ctx.session_id or session_key
        )
          └─> memory.store_conversation_turn(
                user_msg, assistant_msg,
                metadata={"source": "conversation", "role": "chat"},
                user_id="livekit:{sender}",
                session_id=room.name
              )
```

> **The voice write path uses the same `_store_chat_turn_memory` as chat.** This is correct — P11 fixes apply here too.

---

## Gap Analysis

### ✅ What Works (structurally)
- Write path calls `_store_chat_turn_memory` with `user_id=f"livekit:{sender}"` and `session_id=room.name`
- Read path calls `build_for_voice` with same `user_id` and `session_id=memory_session_id`
- `memory_session_id` resolves to `room.name` in the normal LiveKit path
- `retrieve_with_scope_fallback` has session→user fallback for empty session results

### ❌ Gaps to Confirm in Live Smoke

| # | Gap | Risk Level | What to look for in logs |
|---|---|---|---|
| G1 | `user_id` written as `"livekit:{sender}"` — does Chroma have ANY items with this prefix yet? | HIGH | `Items with user_id=livekit:xxx: N` (probe after turn 1) |
| G2 | `VOICE_MEMORY_TIMEOUT_S=0.60s` — may time out before first cold-start embedding | HIGH | `retriever_timeout timeout_s=0.60 origin=voice` |
| G3 | `_should_skip_memory` for voice: only proceeds if `_is_memory_relevant(text)` returns True | MEDIUM | `memory_skipped=true memory_skip_reason=no_recall_trigger` on turn 3 |
| G4 | `context_builder.build_for_voice` uses `retriever=self.memory.retriever` (HybridRetriever) not `memory` (HybridMemoryManager). Does `HybridRetriever` have `retrieve_with_scope_fallback`? | MEDIUM | Confirmed yes at `hybrid_retriever.py:244` |
| G5 | `CONVERSATIONAL_MEMORY_TRIGGERS` patterns: does "what do you know about me" pass voice's `_is_memory_relevant()` check? | MEDIUM | Check pattern list in orchestrator |
| G6 | Voice timeout budget `0.60s` vs chat `2.0s` — warm retriever may still exceed on cold first load | LOW | `memory_retrieve_ms` in logs for voice turns |

---

## CONVERSATIONAL_MEMORY_TRIGGERS — Voice Skip Logic

The key `_should_skip_memory` method at `orchestrator:2089`:
- Identity/capability queries → **always skip**
- `origin != "voice"` → **never skip** (chat always retrieves)
- `origin == "voice"` with `routing_mode_type in ("fast_path", "direct_action")` → **skip**
- `origin == "voice"` with `_is_memory_relevant(text)` True → **retrieve**
- `origin == "voice"` otherwise → **skip (`no_recall_trigger`)**

**The trigger `"what do you know about me"` must match `CONVERSATIONAL_MEMORY_TRIGGERS` to get through. Need to verify this pattern is in the list.**

---

## Config Values at Glance

| Config | Default | Chat equivalent |
|---|---|---|
| `VOICE_MEMORY_MAX_RESULTS` | 2 | 5 (hardcoded) |
| `VOICE_RETRIEVER_K` | 3 (retriever) / 2 (context_builder) | 4 (`CHAT_RETRIEVER_K`) |
| `VOICE_RETRIEVER_K_VECTOR` | 4 | 10 |
| `VOICE_RETRIEVER_K_KEYWORD` | 4 | 10 |
| `VOICE_MEMORY_TIMEOUT_S` | 0.60s | 2.0s |
| `VOICE_RETRIEVER_TIMEOUT_S` | 0.60s | `RETRIEVER_TIMEOUT_S=2.0s` |

> **Note:** `VOICE_RETRIEVER_K` is **inconsistent**: `context_builder.py:409` uses `VOICE_RETRIEVER_K` default `2`, but `hybrid_retriever.py:31` uses default `3`. The context_builder's `k` is what gets passed to `retrieve_with_scope_fallback`, so the effective cap is `min(2, 3) = 2`.

---

## Immediate Next Actions (Before Live Smoke)

### Action 1 — Verify `CONVERSATIONAL_MEMORY_TRIGGERS` covers voice recall queries
```bash
grep -n "CONVERSATIONAL_MEMORY_TRIGGERS" Agent/core/orchestrator/agent_orchestrator.py | head -5
```
Then read the list and confirm `"what do you know about me"` matches.

### Action 2 — Add voice-path memory audit log
In `_retrieve_memory_context_async` (orchestrator:2212), the existing log is:
```
memory_skipped=false ... origin=voice routing_mode_type=...
```
**Add a voice-specific write confirmation log** to `_store_chat_turn_memory` that shows origin:
```python
logger.info("voice_turn_memory_stored user_id=%s session_id=%s origin=%s", user_id, session_id or "none", "voice")
```

### Action 3 — Run 3-turn voice smoke test
Same protocol as P11 console smoke, but over LiveKit:
1. `"my name is Harsha"` (voice)
2. `"what is 2 plus 2"` (voice)
3. `"what do you know about me"` (voice)

**Expected passing logs:**
```
chat_turn_memory_stored user_id=livekit:xxx session_id=<room_name>  # after turn 1
memory_skipped=false ... origin=voice  # turn 3 retrieval
context_builder_memory_sanitized raw_items=N kept_lines=N  # turn 3 build_for_voice
```
**Expected pass condition:** Turn 3 voice response contains "Harsha".

---

## Phase 12 Work Items from This Analysis

| Item | Description | Priority |
|---|---|---|
| P12-01-A | Verify `CONVERSATIONAL_MEMORY_TRIGGERS` pattern set covers voice recall queries | Blocker |
| P12-01-B | Add `origin` tag to `_store_chat_turn_memory` audit log | Before smoke |
| P12-01-C | Run 3-turn live voice smoke, capture full log | Core validation |
| P12-01-D | If G2 fires (timeout): raise `VOICE_MEMORY_TIMEOUT_S` to `1.5s` and re-test | Contingency |
| P12-01-E | If G3 fires (skip): add voice recall trigger patterns like `"what do you know"` | Contingency |