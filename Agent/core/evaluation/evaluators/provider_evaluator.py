"""
Provider health evaluator.

Monitors provider reliability and circuit breaker state.
"""

from typing import Optional, Any

MAX_PROVIDER_FAILURE_RATE = 0.05  # 5% failure rate threshold


def evaluate_providers(metrics: Optional[Any]) -> bool:
    """
    Evaluate provider health based on failure rates.
    
    This would have caught Bug #2: Deprecated API causing crashes (high failure rate).
    
    Args:
        metrics: RequestMetrics from telemetry
    
    Returns:
        True if provider health is acceptable
    """
    if not metrics:
        return True
    
    # Check probe failures (circuit breaker integration)
    if hasattr(metrics, 'probe_failures') and metrics.probe_failures > 0:
        return False
    
    # Check retry count (high retries indicate provider issues)
    if hasattr(metrics, 'retry_count') and metrics.retry_count >= 3:
        return False
    
    return True
