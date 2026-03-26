from __future__ import annotations

import os
import re
from typing import Iterable

from .system_models import SystemAction, SystemActionType


FILE_ACTIONS = {
    SystemActionType.FILE_CREATE,
    SystemActionType.FILE_MOVE,
    SystemActionType.FILE_COPY,
    SystemActionType.FILE_DELETE,
    SystemActionType.FILE_SEARCH,
    SystemActionType.FILE_ORGANIZE,
    SystemActionType.FILE_RENAME,
}

CRITICAL_PROCESS_DENYLIST = {
    "systemd",
    "dbus",
    "dbus-daemon",
    "xorg",
    "x",
    "gnome-shell",
    "wayland",
    "pulseaudio",
    "pipewire",
    "networkmanager",
    "sshd",
    "init",
    "kthreadd",
}


class ActionValidator:
    BLOCKED_PATTERNS = [
        r"rm\s+-rf\s+/",
        r"sudo\s+",
        r"chmod\s+777\s+/",
        r"\bmkfs\b",
        r"\bdd\s+if=",
        r">\s*/dev/",
        r"format\s+[a-zA-Z]:",
        r"\bdeltree\b",
        r":\(\)\{ :\|:& \};:",
    ]
    SAFE_PATH_PREFIXES = [
        os.path.expanduser("~/"),
        "/tmp/",
        "/home/",
    ]

    def validate(self, action: SystemAction) -> tuple[bool, str]:
        command = str(action.params.get("command") or "").strip()
        if command:
            for pattern in self.BLOCKED_PATTERNS:
                if re.search(pattern, command, flags=re.IGNORECASE):
                    return False, f"Blocked dangerous pattern: {pattern}"

        if action.action_type == SystemActionType.PROCESS_KILL:
            target = str(
                action.params.get("pid_or_name")
                or action.params.get("name")
                or action.params.get("pid")
                or ""
            ).strip().lower()
            if target and target in CRITICAL_PROCESS_DENYLIST:
                return False, "Blocked critical process target"

        if action.action_type in FILE_ACTIONS:
            for path in self._iter_candidate_paths(action):
                if not self._is_safe_path(path):
                    return False, f"Path {path} is outside safe boundaries"

        if action.destructive and not action.requires_confirmation:
            action.requires_confirmation = True

        return True, "ok"

    def _iter_candidate_paths(self, action: SystemAction) -> Iterable[str]:
        for key in ("path", "source", "destination"):
            value = action.params.get(key)
            if isinstance(value, str) and value.strip():
                yield value.strip()
        paths = action.params.get("paths")
        if isinstance(paths, list):
            for value in paths:
                if isinstance(value, str) and value.strip():
                    yield value.strip()

    def _is_safe_path(self, path: str) -> bool:
        expanded = os.path.abspath(os.path.expanduser(str(path or "").strip()))
        return any(expanded.startswith(prefix) for prefix in self.SAFE_PATH_PREFIXES)
