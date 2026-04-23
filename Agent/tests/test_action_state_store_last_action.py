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


def _sample_entity(*, value: str = "Narendra Modi") -> dict:
    return {
        "domain": "research",
        "value": value,
        "entity_type": "person",
        "source_query": f"tell me about {value}",
        "written_at_ts": time.time(),
        "written_at_turn": 1,
        "non_research_turns": 0,
    }


def _sample_pending(*, when: str = "tomorrow at 5 pm") -> dict:
    return {
        "type": "set_reminder",
        "domain": "scheduling",
        "summary": f"Pending reminder at {when}",
        "data": {"time": when},
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


def test_active_entity_set_and_get() -> None:
    store = ActionStateStore()
    sid = "entity-1"

    store.increment_turn(sid)
    store.set_active_entity(sid, _sample_entity())

    entity = store.get_active_entity(sid)
    assert entity is not None
    assert entity["value"] == "Narendra Modi"
    assert entity["entity_type"] == "person"


def test_active_entity_overwrite_replaces_previous_value() -> None:
    store = ActionStateStore()
    sid = "entity-2"

    store.increment_turn(sid)
    store.set_active_entity(sid, _sample_entity(value="Narendra Modi"))
    store.set_active_entity(sid, _sample_entity(value="Elon Musk"))

    entity = store.get_active_entity(sid)
    assert entity is not None
    assert entity["value"] == "Elon Musk"


def test_active_entity_expires_by_turn_distance() -> None:
    store = ActionStateStore(
        ActionStateConfig(
            last_action_ttl_seconds=3600,
            last_action_max_turns=5,
            active_entity_ttl_seconds=3600,
            active_entity_max_turns=2,
            active_entity_max_non_research_turns=10,
        )
    )
    sid = "entity-3"
    store.increment_turn(sid)
    entity = _sample_entity()
    entity["written_at_turn"] = store.current_turn(sid)
    store.set_active_entity(sid, entity)

    store.increment_turn(sid)
    store.increment_turn(sid)
    store.increment_turn(sid)

    resolved, reason = store.get_active_entity_with_reason(sid)
    assert resolved is None
    assert reason == "expired_turns"


def test_active_entity_drift_expires_after_non_research_turns() -> None:
    store = ActionStateStore(
        ActionStateConfig(
            active_entity_ttl_seconds=3600,
            active_entity_max_turns=10,
            active_entity_max_non_research_turns=2,
        )
    )
    sid = "entity-4"
    store.increment_turn(sid)
    store.set_active_entity(sid, _sample_entity())

    store.mark_route_turn_sync(sid, "chat")
    store.mark_route_turn_sync(sid, "media_play")
    store.mark_route_turn_sync(sid, "chat")

    resolved, reason = store.get_active_entity_with_reason(sid)
    assert resolved is None
    assert reason == "drifted_context"


def test_pending_scheduling_set_and_get() -> None:
    store = ActionStateStore()
    sid = "pending-1"
    store.increment_turn(sid)
    store.set_pending_scheduling_action(sid, _sample_pending())

    pending = store.get_pending_scheduling_action(sid)
    assert pending is not None
    assert pending["type"] == "set_reminder"
    assert pending["data"]["time"] == "tomorrow at 5 pm"


def test_pending_scheduling_expires_by_turn_distance() -> None:
    store = ActionStateStore(
        ActionStateConfig(
            pending_scheduling_ttl_seconds=3600,
            pending_scheduling_max_turns=2,
        )
    )
    sid = "pending-2"
    store.increment_turn(sid)
    pending = _sample_pending()
    pending["written_at_turn"] = store.current_turn(sid)
    store.set_pending_scheduling_action(sid, pending)

    store.increment_turn(sid)
    store.increment_turn(sid)
    store.increment_turn(sid)

    resolved, reason = store.get_pending_scheduling_action_with_reason(sid)
    assert resolved is None
    assert reason == "expired_turns"


def test_pending_scheduling_clear_removes_value() -> None:
    store = ActionStateStore()
    sid = "pending-3"
    store.increment_turn(sid)
    store.set_pending_scheduling_action(sid, _sample_pending())
    store.clear_pending_scheduling_action(sid)
    assert store.get_pending_scheduling_action(sid) is None
