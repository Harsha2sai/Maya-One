"""
Metrics - Performance tracking and monitoring.
"""
import logging
import time
from typing import Dict, Optional
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

class MetricsCollector:
    """Collects and tracks performance metrics."""
    
    def __init__(self):
        self.counters: Dict[str, int] = defaultdict(int)
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, list] = defaultdict(list)
        self.timers: Dict[str, float] = {}
    
    def increment(self, metric_name: str, value: int = 1):
        """Increment a counter metric."""
        self.counters[metric_name] += value
        logger.debug(f"📊 {metric_name}: {self.counters[metric_name]}")
    
    def set_gauge(self, metric_name: str, value: float):
        """Set a gauge metric (current value)."""
        self.gauges[metric_name] = value
        logger.debug(f"📏 {metric_name}: {value}")
    
    def record_histogram(self, metric_name: str, value: float):
        """Record a value in a histogram."""
        self.histograms[metric_name].append(value)
        # Keep only last 1000 values
        if len(self.histograms[metric_name]) > 1000:
            self.histograms[metric_name] = self.histograms[metric_name][-1000:]
    
    def start_timer(self, metric_name: str):
        """Start a timer for measuring duration."""
        self.timers[metric_name] = time.time()
    
    def stop_timer(self, metric_name: str) -> Optional[float]:
        """Stop a timer and record the duration."""
        if metric_name in self.timers:
            duration = time.time() - self.timers[metric_name]
            self.record_histogram(f"{metric_name}_duration_seconds", duration)
            del self.timers[metric_name]
            logger.debug(f"⏱️ {metric_name}: {duration:.3f}s")
            return duration
        return None
    
    def get_stats(self, metric_name: str) -> Dict:
        """Get statistics for a histogram metric."""
        if metric_name not in self.histograms or not self.histograms[metric_name]:
            return {}
        
        values = self.histograms[metric_name]
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "p50": sorted(values)[len(values) // 2],
            "p95": sorted(values)[int(len(values) * 0.95)],
            "p99": sorted(values)[int(len(values) * 0.99)]
        }
    
    def get_summary(self) -> Dict:
        """Get a summary of all metrics."""
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "histograms": {
                name: self.get_stats(name) 
                for name in self.histograms.keys()
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def reset(self):
        """Reset all metrics."""
        self.counters.clear()
        self.gauges.clear()
        self.histograms.clear()
        self.timers.clear()
        logger.info("🔄 Metrics reset")

# Global metrics instance
metrics = MetricsCollector()
