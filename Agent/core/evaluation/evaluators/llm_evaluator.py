"""
LLM performance evaluator.

Validates LLM latency and token budget to catch performance regressions.
"""

from typing import Optional, Any

# Thresholds based on soak test targets
MAX_FIRST_TOKEN_LATENCY = 3.0  # seconds
MAX_PROMPT_TOKENS = 2000


def evaluate_llm(metrics: Optional[Any]) -> bool:
    """
    Evaluate LLM health based on latency and token budget.
    
    This would have caught Bug #3: High LLM latency (5.7s).
    
    Args:
        metrics: RequestMetrics from telemetry
    
    Returns:
        True if LLM performance is acceptable
    """
    if not metrics:
        return True  # No data yet
    
    # Check first token latency
    latency_ok = True
    if hasattr(metrics, 'stream_first_chunk_latency') and metrics.stream_first_chunk_latency is not None:
        latency_ok = metrics.stream_first_chunk_latency < MAX_FIRST_TOKEN_LATENCY
    
    # Check token budget
    tokens_ok = True
    if hasattr(metrics, 'tokens_in') and metrics.tokens_in is not None:
        tokens_ok = metrics.tokens_in < MAX_PROMPT_TOKENS
    
    return latency_ok and tokens_ok
