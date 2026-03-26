"""
Evaluation layer for continuous runtime health monitoring.

This module provides automated pass/fail decisions for:
- LLM performance (latency, token budget)
- Memory system health (schema, retrieval)
- Provider reliability (circuit breakers, failures)
- Tool execution health
- Long-running stability (memory leaks)
"""

from .health_model import SystemHealth, compute_score
from .evaluation_engine import EvaluationEngine, SystemStats

__all__ = [
    'SystemHealth',
    'compute_score',
    'EvaluationEngine',
    'SystemStats',
]
