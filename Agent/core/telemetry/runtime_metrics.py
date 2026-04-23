
import logging
import json
import time
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class RuntimeMetrics:
    """
    Simple file-based metrics collector for runtime validation.
    """
    _metrics: Dict[str, Any] = {
        "tasks_created_total": 0,
        "tasks_completed_total": 0,
        "tasks_failed_total": 0,
        "task_runtime_seconds": [], # List of floats
        "task_steps_executed_total": 0,
        "task_retries_total": 0,
        "llm_calls_total": 0,
        "worker_step_failures_total": 0,
        "memory_stores_total": 0,
        "memory_queries_total": 0,
        "memory_hits_total": 0,
        "memory_hits_profile_total": 0,
        "memory_hits_vector_total": 0,
        "vector_store_errors_total": 0,
        "last_action_hits_total": 0,
        "last_action_misses_total": 0,
        "active_entity_written": 0,
        "active_entity_followup_hit": 0,
        "pronoun_resolution_success_total": 0,
        "pronoun_resolution_ambiguous_total": 0,
        "scheduling_clarification_requested": 0,
        "scheduling_missing_task_followup_total": 0,
        "pending_scheduling_resume_total": 0,
        "pending_scheduling_expired_total": 0,
        "state_arbiter_decision_total": 0,
        "state_arbiter_ambiguity_total": 0,
        "state_arbiter_clarify_total": 0,
        "state_arbiter_outcome_mismatch_total": 0,
    }
    
    _log_file: Path = Path("verification/runtime_validation/runtime_metrics.json")
    
    @classmethod
    def increment(cls, metric: str, value: int = 1):
        if metric in cls._metrics:
            if isinstance(cls._metrics[metric], int):
                cls._metrics[metric] += value
                cls._flush()
            else:
                logger.warning(f"Metric {metric} is not a counter.")
        else:
            logger.warning(f"Unknown metric {metric}")

    @classmethod
    def observe(cls, metric: str, value: float):
        if metric in cls._metrics:
            if isinstance(cls._metrics[metric], list):
                cls._metrics[metric].append(value)
                cls._flush()
            else:
                logger.warning(f"Metric {metric} is not a histogram.")
        else:
            logger.warning(f"Unknown metric {metric}")

    @classmethod
    def _flush(cls):
        try:
            # Ensure directory exists
            cls._log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cls._log_file, "w") as f:
                json.dump(cls._metrics, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to flush metrics: {e}")

    @classmethod
    def reset(cls):
        cls._metrics = {
             "tasks_created_total": 0,
             "tasks_completed_total": 0,
             "tasks_failed_total": 0,
             "task_runtime_seconds": [],
             "task_steps_executed_total": 0,
             "task_retries_total": 0,
             "llm_calls_total": 0,
             "worker_step_failures_total": 0,
             "memory_stores_total": 0,
             "memory_queries_total": 0,
             "memory_hits_total": 0,
             "memory_hits_profile_total": 0,
             "memory_hits_vector_total": 0,
             "vector_store_errors_total": 0,
             "last_action_hits_total": 0,
             "last_action_misses_total": 0,
             "active_entity_written": 0,
             "active_entity_followup_hit": 0,
             "pronoun_resolution_success_total": 0,
             "pronoun_resolution_ambiguous_total": 0,
             "scheduling_clarification_requested": 0,
             "scheduling_missing_task_followup_total": 0,
             "pending_scheduling_resume_total": 0,
             "pending_scheduling_expired_total": 0,
             "state_arbiter_decision_total": 0,
             "state_arbiter_ambiguity_total": 0,
             "state_arbiter_clarify_total": 0,
             "state_arbiter_outcome_mismatch_total": 0,
        }
        cls._flush()
