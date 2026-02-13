import pytest
import asyncio
import time
from utils.rate_limiter import RateLimiter

@pytest.mark.asyncio
async def test_rate_limiter_allows_calls():
    limiter = RateLimiter(max_calls=2, period=1)
    
    # First call should pass immediately
    start = time.time()
    await limiter.acquire()
    duration = time.time() - start
    assert duration < 0.1

    # Second call should pass immediately
    start = time.time()
    await limiter.acquire()
    duration = time.time() - start
    assert duration < 0.1

@pytest.mark.asyncio
async def test_rate_limiter_blocks_excess_calls():
    limiter = RateLimiter(max_calls=1, period=1)
    
    # First call uses up the capacity
    await limiter.acquire()
    
    # Second call should block for approx 1 second
    start = time.time()
    await limiter.acquire()
    duration = time.time() - start
    
    assert duration >= 0.9  # Approx 1s wait
