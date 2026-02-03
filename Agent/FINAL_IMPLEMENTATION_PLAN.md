# Final Implementation Plan 🛠️

This document details the exact steps to upgrade the LiveKit Agent with Supabase persistence, robust rate limiting, and performance optimizations.

## 1. Prerequisites
- **Git Repository**: No specific repo to pull, we are building on the existing scaffold.
- **Dependencies**:
  - `supabase` (Add to `requirements.txt`)
  - No external rate-limit lib needed (we will implement a simple one).

## 2. Supabase Integration (Persistence)
**Objective**: Replace in-memory lists with Supabase tables.

### 2.1 Schema Setup
The Flutter app already uses Supabase. We must ensure these tables exist. You will need to run the following SQL in your Supabase Dashboard:

```sql
-- (See UPDATE_PLAN.md for full SQL)
-- Key Tables: user_alarms, user_reminders, user_notes
```

### 2.2 Async Supabase Manager
The official `supabase` python client is synchronous. To prevent blocking the real-time audio loop, all DB calls **must** be wrapped in `asyncio.to_thread`.

**File**: `system_control/supabase_manager.py`
```python
import os
import asyncio
import logging
from supabase import create_client, Client
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class SupabaseManager:
    def __init__(self):
        self.client: Optional[Client] = None
        self._init_client()

    def _init_client(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        if url and key:
            self.client = create_client(url, key)
            logger.info("✅ Supabase Client Initialized")
        else:
            logger.warning("⚠️ Supabase Credentials Missing")

    async def create_alarm(self, user_id: str, alarm_time: str, label: str):
        if not self.client: return None
        # Run synchronous client method in a separate thread
        return await asyncio.to_thread(
            lambda: self.client.table("user_alarms").insert({
                "user_id": user_id,
                "alarm_time": alarm_time,
                "label": label
            }).execute()
        )
    
    # ... (Similar async wrappers for get_alarms, delete_alarm, etc.)
```

### 2.3 Updating Tools
Modify `tools.py` to fetch `user_id` from the LiveKit context and call the manager.

**Context Strategy**:
The `context` argument in tools is `RunContext`. We will attach `user_id` to the `JobContext` in `agent.py` and access it here.

```python
@function_tool()
async def set_alarm(context: RunContext, time: str, label: str = "") -> str:
    # 1. Get User ID safely
    user_id = getattr(context.job_context, 'user_id', 'anonymous')
    
    # 2. Persist
    result = await supabase_manager.create_alarm(user_id, time, label)
    
    if result:
        return f"Alarm set for {time}"
    return "Failed to save alarm."
```

## 3. Rate Limiting (Stability)
**Objective**: Prevent hitting Groq's 6000 TPM limit.

**File**: `utils/rate_limiter.py`
```python
import asyncio
import time
from collections import deque

class RateLimiter:
    def __init__(self, max_calls=4, period=60):
        self.calls = deque()
        self.max_calls = max_calls
        self.period = period
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = time.time()
            # Clean old calls
            while self.calls and self.calls[0] < now - self.period:
                self.calls.popleft()
            
            if len(self.calls) >= self.max_calls:
                wait_time = self.calls[0] + self.period - now
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
            
            self.calls.append(time.time())
```

**Integration**: Wrap the `llm.chat()` call in `agent.py` with `await rate_limiter.acquire()`.

## 4. User ID Injection logic
In `agent.py`:
```python
async def entrypoint(ctx: JobContext):
    # Extract Identity
    metadata = ctx.job.metadata or "{}"
    # Parse metadata to get user_id (assumes frontend sends it)
    # If not present, fallback to job.participant.identity
    ctx.user_id = ... 
    
    # ... start agent
```

## 5. Execution Steps
1.  **Stop Backend**: Ensure no zombie processes (`./start_backend.sh` usually handles this).
2.  **Dependencies**: Update `requirements.txt` with `supabase`.
3.  **Codebase Updates**:
    - Create `utils/rate_limiter.py`
    - Create `system_control/supabase_manager.py`
    - Update `agent.py` (Inject User ID, Add Rate Limiter)
    - Update `tools.py` (Use Supabase Manager)
4.  **Database**: Run SQL Migration in Supabase Dashboard.

## 6. Impact Analysis
-   **Audio Latency**: Using `asyncio.to_thread` for DB calls ensures the voice VAD loop is NOT blocked. This is critical.
-   **Cold Start**: First request might be slower due to DB connection, subsequent ones fast.
-   **Stability**: Rate limiter will prevent "429 Too Many Requests" errors from Groq.

## 7. Next Actions for User
-   Provide `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`.
-   Run the provided SQL in Supabase.
