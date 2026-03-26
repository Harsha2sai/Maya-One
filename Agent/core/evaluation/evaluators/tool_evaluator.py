"""
Tool execution evaluator.

Monitors tool pipeline health and execution success rates.
"""

from typing import Optional, Any

MAX_TOOL_FAILURE_RATE = 0.05


def evaluate_tools(metrics: Optional[Any]) -> bool:
    """
    Evaluate tool execution health.
    
    Args:
        metrics: RequestMetrics from telemetry
    
    Returns:
        True if tool execution is healthy
    """
    if not metrics:
        return True
    
    # Tools should execute successfully most of the time
    # High retry counts indicate tool pipeline issues
    if hasattr(metrics, 'retry_count') and metrics.retry_count >= 3:
        return False
    
    return True
