
import asyncio
import json
import logging
from pathlib import Path
import asyncio
import json
import random
import time
from pathlib import Path
from dataclasses import asdict
from telemetry.session_monitor import get_session_monitor, RequestMetrics

class BaselineCollector:
    def __init__(self):
        self.monitor = get_session_monitor()
        self.data = []
        
        # Disable thresholds during collection
        self.monitor.thresholds = {k: {'warning': 99999, 'critical': 99999} for k in self.monitor.thresholds}

    async def run_scenario(self, name, iterations=10):
        print(f"🚀 Collecting baseline for: {name} ({iterations} iterations)")
        
        for i in range(iterations):
            self.monitor.start_request()
            
            # Simulate real-world jitter for different scenarios
            if name == "normal":
                # Typical conversation
                latency = random.uniform(0.8, 2.5)
                first_chunk = random.uniform(0.3, 0.8)
                tokens_in = random.randint(300, 800)
                tokens_out = random.randint(50, 300)
                context = tokens_in + tokens_out
            elif name == "tool":
                # Tool calls usually take longer
                latency = random.uniform(1.5, 4.2)
                first_chunk = random.uniform(0.5, 1.2)
                tokens_in = random.randint(1000, 2500)
                tokens_out = random.randint(100, 500)
                context = tokens_in + tokens_out
                self.monitor.record_metric('tool_calls_count', 1, increment=True)
            elif name == "memory":
                # Memory retrieval overhead
                latency = random.uniform(1.0, 3.0)
                first_chunk = random.uniform(0.4, 0.9)
                tokens_in = random.randint(800, 1500)
                tokens_out = random.randint(50, 200)
                context = tokens_in + tokens_out
                self.monitor.record_metric('memory_retrieval_count', 1, increment=True)
            elif name == "long_conv":
                # High context drift
                latency = random.uniform(2.5, 6.0)
                first_chunk = random.uniform(1.0, 2.5)
                tokens_in = random.randint(4000, 8000)
                tokens_out = random.randint(200, 1000)
                context = tokens_in + tokens_out

            # Apply simulation
            time.sleep(0.01) # Minimal real delay
            self.monitor.record_metric('llm_latency', latency)
            self.monitor.record_metric('stream_first_chunk_latency', first_chunk)
            self.monitor.record_metric('tokens_in', tokens_in)
            self.monitor.record_metric('tokens_out', tokens_out)
            self.monitor.record_metric('context_size', context)
            
            # Record metrics
            metrics = asdict(self.monitor.current_metrics)
            metrics['scenario'] = name
            self.data.append(metrics)
            self.monitor.end_request()

    def save(self, output_path):
        with open(output_path, 'w') as f:
            json.dump(self.data, f, indent=2)
        print(f"✅ Saved {len(self.data)} baseline points to {output_path}")

async def main():
    collector = BaselineCollector()
    
    await collector.run_scenario("normal", iterations=20)
    await collector.run_scenario("tool", iterations=10)
    await collector.run_scenario("memory", iterations=10)
    await collector.run_scenario("long_conv", iterations=10)

    collector.save("telemetry_baseline.json")

if __name__ == "__main__":
    asyncio.run(main())

if __name__ == "__main__":
    asyncio.run(main())
