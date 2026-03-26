import asyncio
import time
from collections import deque

class RateLimiter:
    def __init__(self, max_calls=4, period=60):
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = time.time()
            while self.calls and self.calls[0] < now - self.period:
                self.calls.popleft()
            
            if len(self.calls) >= self.max_calls:
                wait = self.calls[0] + self.period - now
                if wait > 0:
                    import logging
                    logging.getLogger(__name__).info(f"⏳ Rate limit reached, waiting {wait:.2f}s...")
                    await asyncio.sleep(wait)
            self.calls.append(time.time())
