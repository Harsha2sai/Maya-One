
import logging
import asyncio
from telemetry.session_monitor import get_session_monitor

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)

async def test_refined_thresholds():
    monitor = get_session_monitor()
    
    print("\n=== Testing Refined Thresholds ===\n")
    
    print("--- Normal Operation (Should NOT alert) ---")
    monitor.start_request()
    monitor.record_metric('context_size', 1500)  # Well below 8500
    monitor.record_metric('llm_latency', 2.0)     # Well below 5.0
    monitor.record_metric('stream_first_chunk_latency', 0.8)  # Well below 2.5
    monitor.end_request()
    
    print("\n--- High Load (Should trigger WARNING) ---")
    monitor.start_request()
    monitor.record_metric('context_size', 9000)   # Above 8500 warning
    monitor.record_metric('llm_latency', 5.5)     # Above 5.0 warning
    monitor.end_request()
    
    print("\n--- Severe Drift (Should trigger CRITICAL) ---")
    monitor.start_request()
    monitor.record_metric('context_size', 13000)  # Above 12000 critical
    monitor.record_metric('stream_first_chunk_latency', 5.0)  # Above 4.5 critical
    monitor.record_metric('memory_retrieval_count', 6, increment=True)  # Above 5 critical
    monitor.end_request()
    
    print("\n--- Edge Case: Exactly at P95 (Should NOT alert) ---")
    monitor.start_request()
    monitor.record_metric('llm_latency', 4.6)  # Just below 5.0
    monitor.record_metric('context_size', 7500)  # Just below 8500
    monitor.end_request()
    
    print("\n✅ Threshold validation complete!")

if __name__ == "__main__":
    asyncio.run(test_refined_thresholds())
