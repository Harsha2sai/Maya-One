import logging
import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from .types import UserRole

# Configure a specific logger for audit trails
audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)

# Ensure audit logs are written to a file if not already configured
# (This setup assumes standard logging config might not handle 'audit' specifically)
# For now, we rely on the root logger configuration or add a specific handler if needed.
# In a production setup, this would write to a separate file or service.

class AuditLogger:
    """
    Logs all tool execution attempts, decisions, and results for auditing.
    """

    @staticmethod
    def log_attempt(
        tool_name: str, 
        params: Dict[str, Any], 
        user_role: UserRole, 
        user_id: str,
        trace_id: Optional[str] = None
    ) -> str:
        """
        Log an execution attempt. Returns a trace_id for correlation.
        """
        if not trace_id:
            trace_id = str(uuid.uuid4())
            
        entry = {
            "event": "execution_attempt",
            "timestamp": datetime.utcnow().isoformat(),
            "trace_id": trace_id,
            "user_id": user_id,
            "role": user_role.name,
            "tool": tool_name,
            "params": params
        }
        audit_logger.info(json.dumps(entry))
        return trace_id

    @staticmethod
    def log_block(
        trace_id: str, 
        tool_name: str, 
        reason: str
    ):
        """
        Log a blocked execution.
        """
        entry = {
            "event": "execution_blocked",
            "timestamp": datetime.utcnow().isoformat(),
            "trace_id": trace_id,
            "tool": tool_name,
            "reason": reason
        }
        audit_logger.warning(json.dumps(entry))

    @staticmethod
    def log_result(
        trace_id: str, 
        tool_name: str, 
        result: Any,
        success: bool = True
    ):
        """
        Log the result of an execution.
        """
        # Truncate large results for logging
        result_str = str(result)
        if len(result_str) > 1000:
            result_str = result_str[:1000] + "... (truncated)"

        entry = {
            "event": "execution_result",
            "timestamp": datetime.utcnow().isoformat(),
            "trace_id": trace_id,
            "tool": tool_name,
            "success": success,
            "result": result_str
        }
        if success:
            audit_logger.info(json.dumps(entry))
        else:
            audit_logger.error(json.dumps(entry))
