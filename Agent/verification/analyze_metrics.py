
import json
import numpy as np
from typing import List, Dict

def analyze_baseline(file_path: str):
    with open(file_path, 'r') as f:
        data = json.load(f)

    metrics_to_analyze = [
        'tokens_in', 'tokens_out', 'context_size', 
        'llm_latency', 'stream_first_chunk_latency', 
        'tool_calls_count', 'retry_count', 
        'probe_failures', 'memory_retrieval_count'
    ]

    results = {}
    
    # Analyze globally first
    print("============================================================")
    print("📊 BASELINE METRICS DISTRIBUTION")
    print("============================================================")
    print(f"{'Metric':<25} | {'Median':<8} | {'P95':<8} | {'P99':<8} | {'Max':<8}")
    print("-" * 65)

    for metric in metrics_to_analyze:
        values = [d[metric] for d in data if metric in d]
        if not values:
             continue
        
        median = np.median(values)
        p95 = np.percentile(values, 95)
        p99 = np.percentile(values, 99)
        mx = np.max(values)
        
        results[metric] = {
            'median': float(median),
            'p95': float(p95),
            'p99': float(p99),
            'max': float(mx)
        }
        
        print(f"{metric:<25} | {median:8.2f} | {p95:8.2f} | {p99:8.2f} | {mx:8.2f}")

    print("\n💡 SUGGESTED THRESHOLDS (Refined)")
    print("-" * 65)
    print(f"{'Metric':<25} | {'Warning (P95)':<15} | {'Critical (P99)':<15}")
    print("-" * 65)
    
    # Recommended mappings
    mapping = {
        'llm_latency': 'llm_latency',
        'stream_first_chunk_latency': 'first_chunk_latency',
        'context_size': 'context_tokens',
        'memory_retrieval_count': 'memory_retrieval_count',
        'retry_count': 'retries_per_request'
    }

    for metric, threshold_key in mapping.items():
        if metric in results:
            stats = results[metric]
            # Safety margin: ensure we don't set to 0
            warning = max(stats['p95'] * 1.2, 0.5) if stats['p95'] > 0 else 1.0
            critical = max(stats['p99'] * 1.5, 1.0) if stats['p99'] > 0 else 3.0
            
            # Special handling for latency (often has high variance)
            if 'latency' in metric:
                 warning = stats['p95'] + 0.5
                 critical = stats['p99'] + 2.0
            
            print(f"{threshold_key:<25} | {warning:15.2f} | {critical:15.2f}")

if __name__ == "__main__":
    analyze_baseline("telemetry_baseline.json")
