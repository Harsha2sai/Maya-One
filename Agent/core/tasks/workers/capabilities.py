
from core.tasks.task_steps import WorkerType

# 1. Define allowed tools per worker
# This is the single source of truth for permissions.
WORKER_CAPABILITIES = {
    WorkerType.GENERAL: [
        # Task Management
        "list_tasks",
        "get_task_status",
        "ask_task_status",
        "cancel_task",
        "delegate_work",
        # Memory
        "save_memory",
        "retrieve_memory",
        # Explicit Memory Tools (Planner Fallback)
        "create_note",
        "search_memory",
        # Date & Time (read-only, safe for all workers)
        "get_time",
        "get_date",
        "get_current_datetime",
        # Reminder ops (planner may emit these directly for simple scheduling tasks)
        "set_reminder",
        "list_reminders",
        "delete_reminder",
        # Basic info lookups
        "get_weather",
        "web_search",
        "search_web",
        "summarize_url",
    ],
    
    WorkerType.RESEARCH: [
        # Search & Knowledge
        "web_search",
        "search_web",
        "google_search",
        "browser_open",
        "summarize_url",
        "read_url",
        "delegate_work",
        # Task Status
        "get_task_status",
        "ask_task_status",
    ],
    
    WorkerType.AUTOMATION: [
        # Integration
        "send_email",
        "create_calendar_event",
        "spotify_play",
        "reminder_create",
        "delegate_work",
        # File Ops
        "read_file",
        # Task Control
        "get_task_status",
    ],
    
    WorkerType.SYSTEM: [
        # Privileged
        "run_shell_command",
        "system_control",
        "file_write",
        "file_delete",
        "app_control",
        "open_app",
        # Task Control
        "get_task_status",
    ]
}

def get_allowed_tools(worker_type: WorkerType) -> list:
    return WORKER_CAPABILITIES.get(worker_type, [])
