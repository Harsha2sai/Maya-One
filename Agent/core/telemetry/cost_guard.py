
import logging
from typing import Any
from core.tasks.task_models import Task, TaskStatus

logger = logging.getLogger(__name__)

# Safety Limits
MAX_LLM_CALLS_PER_TASK = 30
MAX_TOKENS_PER_TASK = 50000
MAX_TOTAL_RETRIES_PER_TASK = 10

class CostGuard:
    """
    Telemetry guard to prevent excessive resource consumption.
    """
    
    @staticmethod
    def check_usage(task: Task) -> str:
        """
        Check if task has exceeded limits.
        Returns Error message if exceeded, None if OK.
        """
        meta = task.metadata or {}
        
        calls = meta.get("llm_call_count", 0)
        tokens = meta.get("token_usage", 0)
        retries = meta.get("total_retries", 0)
        
        if calls > MAX_LLM_CALLS_PER_TASK:
            return f"⛔ Cost Guard: Exceeded max LLM calls ({MAX_LLM_CALLS_PER_TASK})."
            
        if tokens > MAX_TOKENS_PER_TASK:
             return f"⛔ Cost Guard: Exceeded max token usage ({MAX_TOKENS_PER_TASK})."

        if retries > MAX_TOTAL_RETRIES_PER_TASK:
             return f"⛔ Cost Guard: Exceeded max total retries ({MAX_TOTAL_RETRIES_PER_TASK})."
             
        return None

    @staticmethod
    def log_llm_call(task: Task, tokens: int = 0):
        if task.metadata is None:
            task.metadata = {}
        val = task.metadata.get("llm_call_count", 0)
        task.metadata["llm_call_count"] = val + 1
        
        if tokens > 0:
            t_val = task.metadata.get("token_usage", 0)
            task.metadata["token_usage"] = t_val + tokens
        
    @staticmethod
    def log_retry(task: Task):
        if task.metadata is None:
            task.metadata = {}
        val = task.metadata.get("total_retries", 0)
        task.metadata["total_retries"] = val + 1
