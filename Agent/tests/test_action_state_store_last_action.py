import time

from core.action.constants import ActionStateConfig
from core.action.state_store import ActionStateStore


def _sample_action(*, summary: str = "Reminder: call John at 5pm") -> dict:
    return {
        "type": "set_reminder",
        "domain": "scheduling",
        "summary": summary,
        "data": {"task": "call John", "time": "tomorrow at 5 pm"},
    }


def test_last_action_set_and_get() -> None:
    store = ActionStateStore()
    sid = "s1"

    store.increment_turn(sid)
    store.set_last_action(sid, _sample_action())

    action = store.get_last_action(sid)
    assert action is not None
    assert action["type"] == "set_reminder"
    assert action["domain"] == "scheduling"
    assert action["data"]["task"] == "call John"


def test_last_action_overwrite_replaces_previous_value() -> None:
    store = ActionStateStore()
    sid = "s2"
    store.increment_turn(sid)
    store.set_last_action(sid, _sample_action(summary="Reminder: call John at 5pm"))
    store.set_last_action(sid, _sample_action(summary="Reminder: call Alice at 6pm"))

    action = store.get_last_action(sid)
    assert action is not None
    assert action["summary"] == "Reminder: call Alice at 6pm"


def test_last_action_clear_removes_value() -> None:
    store = ActionStateStore()
    sid = "s3"
    store.increment_turn(sid)
    store.set_last_action(sid, _sample_action())

    store.clear_last_action(sid)
    assert store.get_last_action(sid) is None


def test_last_action_expires_by_ttl() -> None:
    store = ActionStateStore(
        ActionStateConfig(last_action_ttl_seconds=1, last_action_max_turns=10)
    )
    sid = "s4"
    store.increment_turn(sid)
    action = _sample_action()
    action["written_at_ts"] = time.time() - 10
    action["written_at_turn"] = store.current_turn(sid)
    store.set_last_action(sid, action)

    resolved, reason = store.get_last_action_with_reason(sid)
    assert resolved is None
    assert reason == "expired_ttl"


def test_last_action_expires_by_turn_distance() -> None:
    store = ActionStateStore(
        ActionStateConfig(last_action_ttl_seconds=3600, last_action_max_turns=2)
    )
    sid = "s5"
    store.increment_turn(sid)
    action = _sample_action()
    action["written_at_turn"] = store.current_turn(sid)
    store.set_last_action(sid, action)
    store.increment_turn(sid)
    store.increment_turn(sid)
    store.increment_turn(sid)

    resolved, reason = store.get_last_action_with_reason(sid)
    assert resolved is None
    assert reason == "expired_turns"


def test_current_turn_increments() -> None:
    store = ActionStateStore()
    sid = "s6"
    assert store.current_turn(sid) == 0
    assert store.increment_turn(sid) == 1
    assert store.increment_turn(sid) == 2
