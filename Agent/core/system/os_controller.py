from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod


class OSController(ABC):
    @abstractmethod
    def detect_session(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_display_server(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_active_window(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def screenshot(self, path: str) -> bool:
        raise NotImplementedError


class LinuxController(OSController):
    def detect_session(self) -> str:
        session = str(os.environ.get("XDG_SESSION_TYPE", "x11")).strip().lower()
        return session if session in {"x11", "wayland"} else "x11"

    def get_display_server(self) -> str:
        return "xdotool" if self.detect_session() == "x11" else "ydotool"

    def get_active_window(self) -> str:
        if self.get_display_server() != "xdotool":
            return ""
        try:
            window_id = subprocess.check_output(
                ["xdotool", "getactivewindow"],
                text=True,
            ).strip()
            if not window_id:
                return ""
            return subprocess.check_output(
                ["xdotool", "getwindowname", window_id],
                text=True,
            ).strip()
        except Exception:
            return ""

    def screenshot(self, path: str) -> bool:
        try:
            result = subprocess.run(
                ["scrot", path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False


_os_controller: LinuxController | None = None


def get_os_controller() -> LinuxController:
    global _os_controller
    if _os_controller is None:
        _os_controller = LinuxController()
    return _os_controller
