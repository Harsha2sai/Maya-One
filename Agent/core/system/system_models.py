from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SystemActionType(str, Enum):
    FILE_CREATE = "FILE_CREATE"
    FILE_MOVE = "FILE_MOVE"
    FILE_COPY = "FILE_COPY"
    FILE_DELETE = "FILE_DELETE"
    FILE_SEARCH = "FILE_SEARCH"
    FILE_ORGANIZE = "FILE_ORGANIZE"
    FILE_RENAME = "FILE_RENAME"
    APP_LAUNCH = "APP_LAUNCH"
    APP_CLOSE = "APP_CLOSE"
    APP_FOCUS = "APP_FOCUS"
    WINDOW_MOVE = "WINDOW_MOVE"
    WINDOW_RESIZE = "WINDOW_RESIZE"
    WINDOW_MINIMIZE = "WINDOW_MINIMIZE"
    WINDOW_MAXIMIZE = "WINDOW_MAXIMIZE"
    MOUSE_CLICK = "MOUSE_CLICK"
    MOUSE_MOVE = "MOUSE_MOVE"
    KEY_PRESS = "KEY_PRESS"
    TYPE_TEXT = "TYPE_TEXT"
    PROCESS_LIST = "PROCESS_LIST"
    PROCESS_KILL = "PROCESS_KILL"
    SHELL_COMMAND = "SHELL_COMMAND"
    SCREENSHOT = "SCREENSHOT"
    VISION_QUERY = "VISION_QUERY"


@dataclass
class SystemAction:
    action_type: SystemActionType
    params: dict[str, Any] = field(default_factory=dict)
    destructive: bool = False
    requires_confirmation: bool = False
    trace_id: str = ""
    rollback_recipe: dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemResult:
    success: bool
    action_type: SystemActionType
    message: str
    detail: str = ""
    rollback_available: bool = False
    trace_id: str = ""


class ConfirmationState(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
