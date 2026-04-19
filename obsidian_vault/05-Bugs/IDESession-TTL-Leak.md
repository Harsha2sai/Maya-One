# Bug: IDE Session Manager — No TTL Auto-Expiry

**Detected:** 2026-04-19
**Status:** 🟡 OPEN — Low Priority
**File:** `Agent/core/ide/ide_session_manager.py`

## Description
`IDESessionManager` stores open sessions in `self._sessions` dictionary. The `max_concurrent` limit (5 by default) is enforced at `open_session()` time via a count check. However, there is **no TTL (time-to-live) or idle-timeout mechanism**.

If a client:
1. Opens a session (`POST /ide/session/open`) — holds a slot in `_sessions`
2. Crashes / loses reference without calling `POST /ide/session/close`
3. Never calls close again

The session entry in `_sessions` remains **forever**, permanently occupying one of the 5 concurrent slots.

## Impact
- In long-running agent deployments (servers, CI environments), repeated crashed/orphaned clients can permanently exhaust the `max_concurrent` limit
- New clients receive `MaxSessionsExceededError` even though the slots are held by zombie sessions
- Recovery requires agent restart

## Location
```python
# ide_session_manager.py
class IDESessionManager:
    def open_session(self, user_id, ...):
        if len(self._sessions) >= self._max_concurrent:
            raise MaxSessionsExceededError(...)
        self._sessions[session_id] = IDESession(...)
        return session_id
    # No TTL check, no auto-expiry background task
```

## Recommended Fix
Add a TTL mechanism with a background cleanup task:

```python
import asyncio

class IDESessionManager:
    def __init__(self, ..., ttl_seconds: int = 3600):
        ...
        self._ttl_seconds = ttl_seconds
        self._cleanup_task: asyncio.Task | None = None

    async def _start_cleanup(self):
        while True:
            await asyncio.sleep(300)  # every 5 min
            now = time.monotonic()
            expired = [
                sid for sid, s in self._sessions.items()
                if now - s.created_at > self._ttl_seconds
            ]
            for sid in expired:
                await self.close_session(sid)

    def open_session(self, ...):
        ...
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._start_cleanup())
```

## Related
- [[2026-04-19]] — Bug found during vault audit
- `core/ide/ide_session_manager.py` — Affected component

## Priority
**Low** — only manifests with crashed clients and long-running deployments. Not a security issue (slots are isolated per user_id).