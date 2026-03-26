"""
Evaluation engine for continuous runtime health monitoring.

Orchestrates all evaluators and computes system health scores.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Any

from .health_model import SystemHealth, compute_score
from .evaluators.llm_evaluator import evaluate_llm
from .evaluators.memory_evaluator import evaluate_memory, validate_memory_schema
from .evaluators.provider_evaluator import evaluate_providers
from .evaluators.tool_evaluator import evaluate_tools
from .evaluators.stability_evaluator import evaluate_stability

logger = logging.getLogger(__name__)


@dataclass
class SystemStats:
    """System-level statistics for stability evaluation."""
    memory_mb: float


class EvaluationEngine:
    """
    Continuous runtime evaluation engine.
    
    Turns runtime metrics into automated pass/fail decisions.
    This is the "automated QA engineer running in production."
    """
    
    def __init__(self, memory_db_path: Optional[str] = None):
        """
        Initialize evaluation engine.
        
        Args:
            memory_db_path: Path to memory database for schema validation
        """
        self.memory_db_path = memory_db_path
        logger.info("🔍 Evaluation engine initialized")
    
    def evaluate(self, metrics: Optional[Any] = None, system_stats: Optional[SystemStats] = None) -> SystemHealth:
        """
        Evaluate system health based on runtime metrics.
        
        Args:
            metrics: RequestMetrics from telemetry
            system_stats: System-level stats (memory, CPU, etc.)
        
        Returns:
            SystemHealth with overall score
        """
        # Run all evaluators
        llm_ok = evaluate_llm(metrics)
        memory_ok = evaluate_memory(metrics)
        providers_ok = evaluate_providers(metrics)
        tools_ok = evaluate_tools(metrics)
        stability_ok = evaluate_stability(system_stats) if system_stats else True
        
        # Validate schema if memory DB exists
        if self.memory_db_path:
            schema_ok = validate_memory_schema(self.memory_db_path)
            memory_ok = memory_ok and schema_ok
        
        # Compute overall score
        flags = [llm_ok, memory_ok, providers_ok, tools_ok, stability_ok]
        score = compute_score(flags)
        
        health = SystemHealth(
            llm_latency_ok=llm_ok,
            memory_ok=memory_ok,
            providers_ok=providers_ok,
            tools_ok=tools_ok,
            stability_ok=stability_ok,
            overall_score=score
        )
        
        # Log health status
        if not health.is_healthy():
            logger.error(f"🚨 SYSTEM HEALTH DEGRADED: {health}")
        
        return health
