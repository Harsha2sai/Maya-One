# Bug: ConversationTape Concurrency — No Lock on _events

**Detected:** 2026-04-19
**Status:** 🔴 OPEN — Critical
**File:** `Agent/core/orchestrator/conversation_tape.py`

## Severity
**Critical** — Concurrent `append_event` calls can corrupt `self._events` or silently drop events.

## Description
`ConversationTape` uses a plain Python list `self._events` as its primary storage for session events. The `append_event` method performs two non-atomic mutations:

1. `self._events.append(event)` — adds the new event
2. `self._events = self._events[-cap:]` — resizes to enforce the memory cap

Under concurrent async turns (e.g., two parallel `handle_message` calls in the same session), the Python GIL protects individual bytecode operations but NOT the two-step sequence above. A race between two coroutines could:
- **Corrupt the list**: Interleaved append + slice = partially lost events
- **Drop events silently**: Thread A appends, thread B appends, one slice operation overwrites both
- **Raise `IndexError`**: If another coroutine reads `history()` while the slice is being resized

## User Impact
- Silent event loss in concurrent sessions (e.g., two FastAPI requests handled in parallel)
- Debugging nightmare — events appear missing with no error logged
- Pronoun resolution may fail to extract subject from conversation tape under load
- Memory cap behavior becomes unpredictable under concurrent access

## Location
```python
# conversation_tape.py lines 112-114 (approx)
def append_event(self, event):
    self._events.append(event)  # Step 1: not atomic with step 2
    self._events = self._events[-cap:]  # Step 2: resize after append
```

## Recommended Fix
```python
import asyncio

class ConversationTape:
    def __init__(self, ...):
        ...
        self._lock = asyncio.Lock()

    async def append_event(self, event):
        async with self._lock:  # Atomic read-modify-write
            self._events.append(event)
            self._events = self._events[-cap:]

    # Similarly protect history(), get_recent(), etc.
```

**Alternative (simpler):** Use `collections.deque(maxlen=cap)` — `deque.append()` with a maxlen is atomic and automatically discards old items. This eliminates both the concurrency issue and the cap logic.

```python
from collections import deque

class ConversationTape:
    def __init__(self, ...):
        self._events = deque(maxlen=cap)  # atomic append, auto-cap
```

## Related
- [[2026-04-19]] — Bug found during vault audit
- [[ConversationTape]] — Phase 11A Semantic Tape component
- [[Phase 11A: Context Integrity + Semantic Tape]]