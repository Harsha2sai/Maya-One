from __future__ import annotations

import os
import time
from uuid import uuid4

from .safe_shell import safe_shell


class ScreenshotLimiter:
    MAX_PER_TASK = 5
    _count: int = 0
    _task_id: str = ""
    _tmp_files: list[str] = []

    @classmethod
    def reset(cls, task_id: str) -> None:
        cls._cleanup_old_files()
        cls._count = 0
        cls._task_id = str(task_id or "")
        cls._tmp_files = []

    @classmethod
    def take_screenshot(cls) -> tuple[bool, str]:
        if cls._count >= cls.MAX_PER_TASK:
            return False, "screenshot_limit_reached"
        path = f"/tmp/maya_screen_{uuid4().hex[:8]}.png"
        ok, _ = safe_shell(f"scrot {path}")
        if ok:
            cls._count += 1
            cls._tmp_files.append(path)
            return True, path
        return False, path

    @classmethod
    def _cleanup_old_files(cls, max_age_seconds: int = 300) -> None:
        now = time.time()
        retained: list[str] = []
        for path in list(cls._tmp_files):
            if not os.path.exists(path):
                continue
            age = now - os.path.getmtime(path)
            if age > max_age_seconds:
                os.remove(path)
            else:
                retained.append(path)
        cls._tmp_files = retained
