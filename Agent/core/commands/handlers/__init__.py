from .dream import handle_dream
from .flags import handle_flag
from .agent import handle_agents, handle_kill, handle_spawn
from .buddy import handle_buddy, handle_evolve, handle_xp
from .memory import handle_forget, handle_recall, handle_remember
from .mode import handle_lock, handle_mode, handle_unlock
from .project import handle_project
from .rl import handle_rl
from .system import handle_help, handle_reset, handle_status

__all__ = [
    "handle_flag",
    "handle_dream",
    "handle_spawn",
    "handle_agents",
    "handle_kill",
    "handle_buddy",
    "handle_xp",
    "handle_evolve",
    "handle_mode",
    "handle_lock",
    "handle_unlock",
    "handle_project",
    "handle_rl",
    "handle_remember",
    "handle_forget",
    "handle_recall",
    "handle_help",
    "handle_status",
    "handle_reset",
]
