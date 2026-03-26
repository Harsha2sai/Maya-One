"""
Runtime mode configuration for the agent.

Determines whether the agent is running in interactive console mode
or as a background service, which affects logging and background tasks.
"""


class RuntimeMode:
    """Runtime mode constants."""
    INTERACTIVE = "interactive"
    SERVICE = "service"


# Global runtime mode state
current_mode = RuntimeMode.SERVICE


def is_interactive():
    """Check if the agent is running in interactive console mode.
    
    Returns:
        bool: True if in interactive mode, False otherwise
    """
    return current_mode == RuntimeMode.INTERACTIVE


def set_interactive():
    """Set the runtime mode to interactive."""
    global current_mode
    current_mode = RuntimeMode.INTERACTIVE


def set_service():
    """Set the runtime mode to service."""
    global current_mode
    current_mode = RuntimeMode.SERVICE
