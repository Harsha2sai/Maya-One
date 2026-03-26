from core.tasks.workers.tool_registry import WorkerToolRegistry


class _Tool:
    def __init__(self, name: str):
        self.name = name


def test_worker_tool_registry_invariant_baseline_passes():
    WorkerToolRegistry.set_canonical_tools(
        {
            "create_task": _Tool("create_task"),
            "list_tasks": _Tool("list_tasks"),
            "get_task_status": _Tool("get_task_status"),
            "cancel_task": _Tool("cancel_task"),
            "web_search": _Tool("web_search"),
            "run_shell_command": _Tool("run_shell_command"),
            "send_email": _Tool("send_email"),
        }
    )
    assert WorkerToolRegistry.assert_invariants() is True


def test_worker_tool_registry_invariant_detects_missing_baseline():
    WorkerToolRegistry.set_canonical_tools({"list_tasks": _Tool("list_tasks")})
    assert WorkerToolRegistry.assert_invariants() is False
