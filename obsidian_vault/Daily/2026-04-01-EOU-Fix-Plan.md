# Voice Agent EOU/Turn Detection Fix Plan

**Date:** 2026-04-01
**Status:** Planning Complete — Ready for Implementation
**Impact:** High (fixes voice fragment routing + backend disconnect detection)

---

## Executive Summary

After thorough analysis of the Maya agent architecture, Obsidian documentation, and industry best practices (LiveKit EOU model, multi-turn voice agent design), this plan addresses **three independent failure modes**:

1. **Voice turns fragment before routing** — STT fires on "just" mid-sentence, triggering incorrect research routes
2. **Router classifies in isolation** — `AgentRouter` has no conversation history, so continuations like "yes" or "just a small one" are misrouted
3. **Flutter doesn't detect backend death** — LiveKit room persists after agent dies, so Flutter shows "connected" but agent is unresponsive

---

## Root Cause Analysis

### Failure Mode 1: Turn Fragmentation

**Location:** `agent.py:2009-2144` (`_on_user_input_transcribed`)

Current flow:
```
STT fires → is_final check → voice_turn_coalescer → grace delay → dispatch to orchestrator
```

The `voice_turn_coalescer` helps coalesce segments, but EOU decision is primarily driven by VAD silence detection. When a user says "That is just a small app that I want...", the STT may fire on "just" as an interim segment that VAD incorrectly marks as final.

**The Gap:** No semantic completeness check. VAD only knows *when* speech stopped, not *whether* the thought was complete.

### Failure Mode 2: Stateless Routing

**Location:** `core/orchestrator/agent_router.py` + `core/orchestrator/agent_orchestrator.py`

`AgentRouter.route()` receives `utterance` and `user_id` but **NO conversation history**. It cannot know:
- Previous turn was "create an app"
- "Just a small one" is a continuation
- "Yes" is confirming a previous question

**The Architecture Already Has `chat_ctx`:**
- LiveKit's `AgentSession` maintains `chat_ctx` internally
- `agent.py` has `_chat_ctx_messages(chat_ctx)` helper (line 1531)
- Orchestrator accesses `self.agent.chat_ctx` in `_phase6_context_builder_path` (line 4177)

**The Gap:** `chat_ctx` is not passed to `AgentRouter.route()`.

### Failure Mode 3: Research as Implicit Fallback

A fragment like "just" won't match research patterns, but short utterances with no verb should never trigger research. The current research patterns are broad:
```python
_RESEARCH_FRESHNESS_PATTERNS = (
    r"\bwho is (?:the )?(?:current )?(?:ceo|cto|...)\b",
    ...
)
```

---

## Industry Best Practices

### LiveKit EOU Model

LiveKit's **EOUModel** (135M parameter transformer) provides:
- **98.8% accuracy** on completed turns
- **87.5% accuracy** on incomplete utterances (true negatives)
- **85% reduction** in unintentional interruptions

**Key Insight:** VAD alone only knows *when* speech stopped. EOU adds semantic understanding of *whether the thought is complete*.

From LiveKit documentation:
> "A phrase like 'I understand your point, but...' would be called an end of turn by VAD, but a human would keep listening. The EOU model reduces unintentional interruptions by 85%."

### Multi-Turn Intent Classification

From voice agent design best practices:

> "Track context variables and include relevant dialogue history in prompts. For multi-turn intent: use hybrid approaches combining pattern matching for common intents with LLM classification for complex cases, with confidence thresholds."

---

## Recommended Fix Plan

### Fix 1: Enable LiveKit EOU Model

**File:** `Agent/agent.py` — where `AgentSession` is constructed

**Current:** Using `min_endpointing_delay`/`max_endpointing_delay` with VAD only.

**Change:**
```python
from livekit.plugins.turn_detector import EOUModel

session = AgentSession(
    vad=silero.VAD.load(),
    turn_detection=EOUModel(),  # Add semantic turn detection
    min_endpointing_delay=1.0,  # Slightly raise minimum
    max_endpointing_delay=6.0,
    # ... rest of config
)
```

**Why:** EOU model uses conversation context to predict turn completion. "Just" followed by more speech will NOT be marked as final.

---

### Fix 2: Add Pre-Routing Utterance Completeness Guard

**File:** `Agent/core/orchestrator/agent_orchestrator.py` — at `handle_message()` entry

Add guard function:
```python
def _is_complete_utterance(message: str, chat_ctx_items: list, origin: str) -> tuple[bool, str]:
    """Returns (is_complete, reason). Incomplete utterances route to CONVERSATION."""
    if origin != "voice":
        return True, "not_voice"
    
    words = message.strip().split()
    word_count = len(words)
    
    # Fast-path commands that ARE complete even when short
    fast_path_words = {"pause", "stop", "play", "resume", "yes", "no", "ok", "okay", "sure", "thanks"}
    if word_count == 1 and words[0].lower() in fast_path_words:
        return True, "single_word_command"
    
    # Short utterances with continuation markers are incomplete
    continuation_starters = {"just", "and", "also", "but", "so", "then", "that", "which"}
    if word_count <= 4 and words[0].lower() in continuation_starters:
        if chat_ctx_items:  # Has prior context → this is continuation
            return False, "continuation_fragment"
    
    # Very short utterances (< 3 words) with no verb → incomplete
    verbs = {"is", "are", "was", "were", "do", "does", "did", "can", "could", "would", "should", 
             "will", "have", "has", "had", "go", "make", "get", "take", "give", "create", "build"}
    if word_count < 3:
        has_verb = any(w.lower() in verbs for w in words)
        if not has_verb:
            return False, "fragment_no_verb"
    
    return True, "complete"
```

**Use in `handle_message()`:**
```python
# After line 3093 (after _update_turn_identity)
chat_ctx = getattr(self.agent, "chat_ctx", None)
chat_ctx_items = list(chat_ctx.messages) if chat_ctx else []

is_complete, reason = _is_complete_utterance(message, chat_ctx_items, origin)
if not is_complete:
    logger.info("utterance_incomplete reason=%s text=%s", reason, message[:50])
    return await self._handle_chat_response(
        message, user_id, tool_context=tool_context, origin=origin,
    )
```

---

### Fix 3: Pass Conversation Context to AgentRouter

**File:** `Agent/core/orchestrator/agent_router.py`

**Current signature:**
```python
async def route(self, utterance: str, user_id: str) -> str:
```

**New signature:**
```python
async def route(self, utterance: str, user_id: str, chat_ctx: list = None) -> str:
```

Add context-aware routing:
```python
async def route(self, utterance: str, user_id: str, chat_ctx: list = None) -> str:
    chat_ctx = chat_ctx or []
    
    # Extract last assistant/user messages for context
    last_assistant_msg = None
    last_user_msg = None
    for msg in reversed(chat_ctx):
        role = getattr(msg, "role", "")
        content = getattr(msg, "content", "") or ""
        if isinstance(content, list):
            content = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
        if role == "assistant" and last_assistant_msg is None:
            last_assistant_msg = content
        elif role == "user" and last_user_msg is None:
            last_user_msg = content
        if last_assistant_msg and last_user_msg:
            break
    
    # If assistant just asked a question, treat short replies as conversation
    if last_assistant_msg:
        question_patterns = [r'\?$', r'\b(or|would|could|should|do|is|are|can)\s+you\b']
        looks_like_question = any(re.search(p, last_assistant_msg) for p in question_patterns)
        if looks_like_question and len(utterance.split()) <= 8:
            return "chat"  # Answer to question, not new intent
    
    # ... rest of existing routing logic
```

**Update call site in `agent_orchestrator.py`:**
```python
chat_ctx = getattr(self.agent, "chat_ctx", None)
chat_ctx_items = list(chat_ctx.messages) if chat_ctx else []
route_result = await self._router.route(message, user_id, chat_ctx_items)
```

---

### Fix 4: Add Agent Liveness Heartbeat

**Backend (`Agent/agent.py`):**
```python
import asyncio
import json
import time
from livekit import rtc

async def _agent_heartbeat_loop(room: rtc.Room, interval_seconds: float = 5.0):
    """Sends liveness pings over data channel every interval."""
    while True:
        try:
            payload = json.dumps({"type": "agent_heartbeat", "ts": time.time()}).encode()
            await room.local_participant.publish_data(
                payload,
                kind=rtc.DataPacketKind.RELIABLE,
                topic="maya.liveness"
            )
        except Exception as e:
            logger.debug("heartbeat_publish_failed error=%s", e)
        await asyncio.sleep(interval_seconds)

# Start in entrypoint after session starts
heartbeat_task = asyncio.create_task(_agent_heartbeat_loop(ctx.room))
```

**Flutter (`lib/state/providers/session_provider.dart`):**
```dart
Timer? _heartbeatWatchdog;
static const _heartbeatTimeoutMs = 15000; // 15 seconds (3x interval)

void _onDataReceived(DataReceivedEvent event) {
  try {
    final payload = jsonDecode(utf8.decode(event.data));
    if (payload['type'] == 'agent_heartbeat') {
      _resetHeartbeatWatchdog();
    }
  } catch (_) {}
}

void _resetHeartbeatWatchdog() {
  _heartbeatWatchdog?.cancel();
  _heartbeatWatchdog = Timer(
    Duration(milliseconds: _heartbeatTimeoutMs),
    () {
      _updateConnectionState(SessionConnectionState.disconnected);
      _emitLifecycleEvent('agent_heartbeat_timeout');
    },
  );
}
```

---

## Implementation Sequence

Implement in this order — each fix is independently deployable:

| Order | Fix | Impact | Risk |
|-------|-----|--------|------|
| 1 | **Fix 3**: Context-aware router | Highest | Zero (just threading `chat_ctx`) |
| 2 | **Fix 2**: Utterance guard | High | Low (defense-in-depth) |
| 3 | **Fix 1**: EOU model | High | Low (config change) |
| 4 | **Fix 4**: Heartbeat | Medium | Low (self-contained) |

---

## Test Cases

### Voice/EOU Tests

| Input | Context | Expected Behavior |
|-------|---------|-------------------|
| "just" (fragment) | — | Route to CONVERSATION, ask clarification |
| "yes" | After "create an app?" | Route to CONVERSATION (confirmation) |
| "just a small one" | After "what size?" | Route to CONVERSATION (continuation) |
| "search for house budget apps" | — | Route to RESEARCH (explicit intent) |
| "play some music" | — | Route to MEDIA_PLAY (explicit intent) |
| "my name is Harsha" → "what do you know about me" | Memory context | Memory retrieval works |

### Disconnect Tests

| Scenario | Expected Behavior |
|----------|-------------------|
| Backend killed while Flutter connected | UI shows disconnected within 15 seconds |
| Network interruption (LiveKit disconnects) | Existing reconnection logic handles |
| Backend hangs (no crash) | Heartbeat timeout fires, shows disconnected |

---

## Files to Modify

| File | Change |
|------|--------|
| `Agent/agent.py` | Add EOU model, add heartbeat loop |
| `Agent/core/orchestrator/agent_orchestrator.py` | Add `_is_complete_utterance` guard, thread `chat_ctx` |
| `Agent/core/orchestrator/agent_router.py` | Add `chat_ctx` parameter, context-aware routing |
| `Orginal-agent-starter-flutter-main/lib/state/providers/session_provider.dart` | Add heartbeat watchdog |

---

## What NOT to Do

1. **Don't remove the intent routing layer** — Your `AgentRouter` provides deterministic fast paths for common intents. The issue isn't the router existing; it's that it doesn't have conversation context.

2. **Don't replace the router with LLM-only decisions** — Your hybrid approach (patterns for known intents, LLM for ambiguous cases) is correct.

3. **Don't add more mode categories** — Your current categories (identity, media_play, research, system, scheduling, chat) are correct. The fix is better routing inputs, not more routing outputs.

---

## Sources

- [LiveKit EOU Model Documentation](https://docs.livekit.io/reference/python/v1/livekit/plugins/turn_detector/base.html)
- [LiveKit Turns Overview](https://docs.livekit.io/agents/build/turn-detection/configuration/)
- [LiveKit Blog: Using a Transformer to Improve End of Turn Detection](https://www.livekit.io/blog/using-a-transformer-to-improve-end-of-turn-detection)
- [How does end-of-utterance detection work?](https://kb.livekit.io/articles/6569137565-how-does-end-of-utterance-detection-work-in-conversations)
- [Voice Agent Design Best Practices - Google Cloud](https://docs.cloud.google.com/dialogflow/cx/docs/concept/voice-agent-design)
- [Multi-Turn AI Conversations Guide](https://promptagent.uk/the-ultimate-guide-to-multi-turn-ai-conversations-crafting-smarter-more-natural-dialogue/)

---

## Related

- [[01-Architecture/Intent-First Routing]]
- [[01-Architecture/7-Layer Runtime Chain]]
- [[02-Components/ExecutionRouter]]
- [[P12-01 Voice Path Memory]]

---

*Plan created: 2026-04-01*