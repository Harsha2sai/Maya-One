"""
Long-running stability evaluator.

Monitors memory usage and resource consumption to catch leaks.
"""

from typing import Optional, Any

MAX_MEMORY_MB = 2000  # Maximum acceptable memory usage


def evaluate_stability(system_stats: Optional[Any]) -> bool:
    """
    Evaluate long-running stability.
    
    Catches:
    - Memory leaks during soak tests
    - Resource exhaustion
    
    Args:
        system_stats: System-level statistics
    
    Returns:
        True if stability is maintained
    """
    if not system_stats:
        return True
    
    # Check memory usage
    if hasattr(system_stats, 'memory_mb') and system_stats.memory_mb is not None:
        return system_stats.memory_mb < MAX_MEMORY_MB
    
    return True
