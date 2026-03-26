from __future__ import annotations

import time

from core.system.rate_limiter import SystemRateLimiter


def setup_function() -> None:
    SystemRateLimiter._action_count = 0
    SystemRateLimiter._task_timestamps = []
    SystemRateLimiter._last_click_time = 0.0


def test_blocks_after_10_actions() -> None:
    SystemRateLimiter._action_count = 10
    ok, message = SystemRateLimiter.check_action("task")
    assert not ok
    assert "Action limit reached" in message


def test_blocks_after_5_tasks_per_minute(monkeypatch) -> None:
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    SystemRateLimiter._task_timestamps = [now - 1, now - 2, now - 3, now - 4, now - 5]
    ok, message = SystemRateLimiter.check_task()
    assert not ok
    assert "Too many system tasks" in message


def test_click_rate_enforced(monkeypatch) -> None:
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda value: sleeps.append(value))
    SystemRateLimiter._last_click_time = time.time()
    ok, _ = SystemRateLimiter.check_click()
    assert ok
    assert sleeps


def test_reset_clears_action_count() -> None:
    SystemRateLimiter._action_count = 5
    SystemRateLimiter.reset_task()
    assert SystemRateLimiter._action_count == 0


def test_task_window_rolls_correctly(monkeypatch) -> None:
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    SystemRateLimiter._task_timestamps = [now - 61, now - 30]
    ok, _ = SystemRateLimiter.check_task()
    assert ok
    assert len(SystemRateLimiter._task_timestamps) == 2


def test_allows_within_limits() -> None:
    ok, message = SystemRateLimiter.check_action("task")
    assert ok
    assert message == "ok"


def test_concurrent_tasks_counted(monkeypatch) -> None:
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    for _ in range(4):
        ok, _ = SystemRateLimiter.check_task()
        assert ok
    ok, _ = SystemRateLimiter.check_task()
    assert ok
    blocked, _ = SystemRateLimiter.check_task()
    assert not blocked


def test_rate_limit_message_is_clean() -> None:
    SystemRateLimiter._action_count = 10
    _, message = SystemRateLimiter.check_action("task")
    assert "traceback" not in message.lower()
