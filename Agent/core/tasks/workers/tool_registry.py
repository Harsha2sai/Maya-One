import logging
from typing import List, Any, Dict

from core.tasks.task_steps import WorkerType
from core.tasks.workers.capabilities import get_allowed_tools

logger = logging.getLogger(__name__)


class WorkerToolRegistry:
    """
    Adapter over the canonical ToolManager map.

    ToolManager is the source of truth for executable tool objects.
    This registry only filters those tools per worker capability policy.
    """

    _canonical_tools: Dict[str, Any] = {}

    @classmethod
    def set_canonical_tools(cls, tool_map: Dict[str, Any]) -> None:
        normalized: Dict[str, Any] = {}
        for name, tool in (tool_map or {}).items():
            key = str(name or "").strip().lower()
            if key:
                normalized[key] = tool
        cls._canonical_tools = normalized

    @classmethod
    def register_tool(cls, tool: Any):
        """Backward-compatible adapter API used by older tests/callers."""
        name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
        if not isinstance(name, str) or not name.strip():
            return
        key = name.strip().lower()
        cls._canonical_tools[key] = tool

    @classmethod
    def register_tools(cls, tools: List[Any]):
        """Backward-compatible adapter API used by older tests/callers."""
        for t in tools:
            cls.register_tool(t)

    @classmethod
    def get_tools_for_worker(cls, worker_type: WorkerType) -> List[Any]:
        """Return executable canonical tool objects allowed for a worker."""
        allowed_names = {name.lower().strip() for name in get_allowed_tools(worker_type)}
        result = []
        for tool_name in allowed_names:
            tool_obj = cls._canonical_tools.get(tool_name)
            if tool_obj is not None:
                result.append(tool_obj)
        return result

    @classmethod
    def is_tool_allowed(cls, worker_type: WorkerType, tool_name: str) -> bool:
        allowed_names = {n.lower().strip() for n in get_allowed_tools(worker_type)}
        return str(tool_name or "").strip().lower() in allowed_names

    @classmethod
    def get_registry_mismatches(cls) -> Dict[str, List[str]]:
        """
        Return capability-vs-canonical mismatches for startup invariants.
        """
        mismatches: Dict[str, List[str]] = {}
        required_baseline = {"create_task", "list_tasks", "get_task_status", "cancel_task"}
        missing_baseline = [name for name in sorted(required_baseline) if name not in cls._canonical_tools]
        if missing_baseline:
            mismatches["baseline"] = missing_baseline

        # Ensure each worker has at least one callable tool after policy filtering.
        for worker in WorkerType:
            if not cls.get_tools_for_worker(worker):
                mismatches.setdefault(worker.value, []).append("NO_CALLABLE_TOOLS")
        return mismatches

    @classmethod
    def assert_invariants(cls) -> bool:
        mismatches = cls.get_registry_mismatches()
        if mismatches:
            logger.error(f"❌ Worker tool registry mismatch detected: {mismatches}")
            return False
        logger.info("✅ Worker tool registry invariants satisfied")
        return True
