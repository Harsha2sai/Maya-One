"""
Health model for system evaluation.

Defines what a "healthy system" means with boolean flags and overall score.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class SystemHealth:
    """
    System health status with component-level flags.
    
    Attributes:
        llm_latency_ok: LLM latency within acceptable bounds
        memory_ok: Memory system functioning correctly
        providers_ok: Provider health acceptable
        tools_ok: Tool execution healthy
        stability_ok: Long-running stability maintained
        overall_score: 0.0-1.0 health score
    """
    llm_latency_ok: bool
    memory_ok: bool
    providers_ok: bool
    tools_ok: bool
    stability_ok: bool
    overall_score: float
    
    def is_healthy(self) -> bool:
        """
        Check if system is healthy.
        
        Returns:
            True if overall score >= 0.8
        """
        return self.overall_score >= 0.8


def compute_score(flags: List[bool]) -> float:
    """
    Compute health score from boolean flags.
    
    Args:
        flags: List of boolean health indicators
    
    Returns:
        Score between 0.0 and 1.0
    """
    if not flags:
        return 0.0
    return sum(flags) / len(flags)
