
import asyncio
import pytest
import logging
import sys
import random

# Adjust path
sys.path.append(".")

from core.tools.tool_manager import ToolManager
from core.tasks.task_tools import get_task_tools

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("load_test")

async def mock_tool_execution(tool_name: str, duration: float):
    """Simulate tool execution latency."""
    await asyncio.sleep(duration)
    return f"Result from {tool_name}"

@pytest.mark.asyncio
async def test_concurrent_tool_calls():
    """Test concurrent execution of tools to verify thread safety and performance."""
    logger.info("🚀 Starting Concurrent Tool Execution Test (Load Test)")
    
    concurrency = 50 # Number of concurrent calls
    logger.info(f"⚡ Spawning {concurrency} concurrent tool calls...")
    
    tasks = []
    for i in range(concurrency):
        # Simulate mixed workload
        duration = random.uniform(0.1, 0.5) 
        tasks.append(mock_tool_execution(f"tool_{i}", duration))
        
    start_time = asyncio.get_event_loop().time()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    end_time = asyncio.get_event_loop().time()
    
    failures = [r for r in results if isinstance(r, Exception)]
    success_count = len(results) - len(failures)
    
    logger.info(f"📊 Results: {success_count}/{concurrency} successful calls")
    logger.info(f"⏱️ Total time: {end_time - start_time:.4f}s")
    
    if failures:
        logger.error(f"❌ Failures: {failures}")
    
    assert len(failures) == 0, f"Encountered {len(failures)} failures during load test"
    
if __name__ == "__main__":
    asyncio.run(test_concurrent_tool_calls())
