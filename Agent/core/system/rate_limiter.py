from __future__ import annotations

import time


class SystemRateLimiter:
    MAX_ACTIONS_PER_TASK = 10
    MAX_TASKS_PER_MINUTE = 5
    MAX_CLICKS_PER_SECOND = 3

    _action_count: int = 0
    _task_timestamps: list[float] = []
    _last_click_time: float = 0.0

    @classmethod
    def check_action(cls, task_id: str) -> tuple[bool, str]:
        if cls._action_count >= cls.MAX_ACTIONS_PER_TASK:
            return False, "Action limit reached for this task (max 10)"
        return True, "ok"

    @classmethod
    def check_task(cls) -> tuple[bool, str]:
        now = time.time()
        cls._task_timestamps = [stamp for stamp in cls._task_timestamps if now - stamp < 60]
        if len(cls._task_timestamps) >= cls.MAX_TASKS_PER_MINUTE:
            return False, "Too many system tasks - please wait a moment"
        cls._task_timestamps.append(now)
        return True, "ok"

    @classmethod
    def check_click(cls) -> tuple[bool, str]:
        now = time.time()
        interval = 1 / cls.MAX_CLICKS_PER_SECOND
        if now - cls._last_click_time < interval:
            time.sleep(interval - (now - cls._last_click_time))
        cls._last_click_time = time.time()
        return True, "ok"

    @classmethod
    def increment_action(cls) -> None:
        cls._action_count += 1

    @classmethod
    def reset_task(cls) -> None:
        cls._action_count = 0
