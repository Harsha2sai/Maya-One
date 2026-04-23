import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.orchestrator.agent_orchestrator import AgentOrchestrator


def _seed_reminder_action(orchestrator: AgentOrchestrator, session_id: str = "s1") -> None:
    orchestrator._set_last_action_for_context(
        action={
            "type": "set_reminder",
            "domain": "scheduling",
            "summary": "Reminder: call John tomorrow at 5 pm.",
            "data": {"task": "call John", "time": "tomorrow at 5 pm"},
            "written_at_ts": time.time(),
            "written_at_turn": orchestrator._current_action_state_turn(
                SimpleNamespace(session_id=session_id)
            ),
        },
        tool_context=SimpleNamespace(session_id=session_id),
    )


@pytest.mark.asyncio
async def test_followup_what_bypasses_router_and_parser() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    session = SimpleNamespace(session_id="s1")
    _seed_reminder_action(orchestrator, session.session_id)
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="scheduling")

    response = await orchestrator._handle_chat_response(
        "what reminder did you set",
        user_id="u1",
        tool_context=session,
        origin="chat",
    )

    assert "remind you to call john" in response.display_text.lower()
    assert isinstance(response.structured_data, dict)
    assert "_last_action_followup" in response.structured_data
    assert orchestrator._router.route.await_count == 0


@pytest.mark.asyncio
async def test_followup_when_returns_time_phrase() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    session = SimpleNamespace(session_id="s1")
    _seed_reminder_action(orchestrator, session.session_id)
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="identity")

    response = await orchestrator._handle_chat_response(
        "when is it",
        user_id="u1",
        tool_context=session,
        origin="chat",
    )

    assert response.display_text.lower().startswith("it's set for")
    assert "tomorrow at 5 pm" in response.display_text.lower()
    assert orchestrator._router.route.await_count == 0


@pytest.mark.asyncio
async def test_unrelated_query_does_not_trigger_followup_interceptor() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    session = SimpleNamespace(session_id="s1")
    _seed_reminder_action(orchestrator, session.session_id)
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="identity")

    response = await orchestrator._handle_chat_response(
        "what is the time",
        user_id="u1",
        tool_context=session,
        origin="chat",
    )

    assert response.display_text
    if isinstance(response.structured_data, dict):
        assert "_last_action_followup" not in response.structured_data


@pytest.mark.asyncio
async def test_identity_help_query_does_not_trigger_followup_interceptor() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    session = SimpleNamespace(session_id="s1")
    _seed_reminder_action(orchestrator, session.session_id)
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="identity")

    response = await orchestrator._handle_chat_response(
        "what can you do",
        user_id="u1",
        tool_context=session,
        origin="chat",
    )

    assert response.display_text
    assert orchestrator._router.route.await_count == 1
    if isinstance(response.structured_data, dict):
        assert "_last_action_followup" not in response.structured_data


@pytest.mark.asyncio
async def test_stale_last_action_does_not_intercept_followup() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    session = SimpleNamespace(session_id="s1")
    _seed_reminder_action(orchestrator, session.session_id)
    store = orchestrator._action_state_store
    assert store is not None
    for _ in range(8):
        store.increment_turn(session.session_id)

    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="identity")
    response = await orchestrator._handle_chat_response(
        "what reminder did you set",
        user_id="u1",
        tool_context=session,
        origin="chat",
    )

    assert "don't have that recent reminder in context anymore" in response.display_text.lower()
    assert orchestrator._router.route.await_count == 0
    assert isinstance(response.structured_data, dict)
    assert response.structured_data["_last_action_followup"]["reason"] == "expired_turns"


@pytest.mark.asyncio
async def test_no_last_action_routes_normally() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    session = SimpleNamespace(session_id="s1")
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="identity")

    response = await orchestrator._handle_chat_response(
        "what reminder did you set",
        user_id="u1",
        tool_context=session,
        origin="chat",
    )

    assert "don't see any reminder set yet" in response.display_text.lower()
    assert orchestrator._router.route.await_count == 0
