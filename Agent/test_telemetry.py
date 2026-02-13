
import logging
import asyncio
import time
from telemetry.session_monitor import get_session_monitor

# Configure logging to see the telemetry output
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)

async def test_telemetry():
    monitor = get_session_monitor()
    
    print("\n--- Testing Normal Request ---")
    monitor.start_request()
    monitor.record_metric('context_size', 1000)
    monitor.record_metric('stream_first_chunk_latency', 0.5)
    monitor.record_metric('llm_latency', 1.2)
    monitor.record_metric('tokens_out', 150)
    monitor.end_request()
    
    print("\n--- Testing Latency Warning ---")
    monitor.start_request()
    monitor.record_metric('llm_latency', 5.0) # Warning is 4.0
    monitor.end_request()
    
    print("\n--- Testing Critical Thresholds ---")
    monitor.start_request()
    monitor.record_metric('context_size', 7000) # Critical is 6000
    monitor.record_metric('stream_first_chunk_latency', 5.0) # Critical is 4.0
    monitor.record_metric('retry_count', 4) # Critical is 3
    monitor.end_request()

    print("\n--- Testing Incremental Counters ---")
    monitor.start_request()
    monitor.record_metric('tool_calls_count', 1, increment=True)
    monitor.record_metric('tool_calls_count', 1, increment=True)
    monitor.record_metric('memory_retrieval_count', 5, increment=True)
    monitor.record_metric('memory_retrieval_count', 20, increment=True) # Warning is 20
    monitor.end_request()

if __name__ == "__main__":
    asyncio.run(test_telemetry())
