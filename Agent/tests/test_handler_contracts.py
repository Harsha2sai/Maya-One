from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.orchestrator.agent_orchestrator import AgentOrchestrator
from core.orchestrator.media_handler import MediaHandler
from core.orchestrator.research_handler import ResearchHandler
from core.orchestrator.scheduling_handler import SchedulingHandler
from core.response.agent_response import AgentResponse
from core.response.response_formatter import ResponseFormatter


def _response(text: str) -> AgentResponse:
    return ResponseFormatter.build_response(text)


class _AsyncCallRecorder:
    def __init__(self, return_value):
        self.return_value = return_value
        self.calls = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.return_value


def test_scheduling_task_followup_matcher_rejects_conversational_queries():
    assert SchedulingHandler._looks_like_reminder_task_followup("tell me more about him") is False
    assert SchedulingHandler._looks_like_reminder_task_followup("what is my name") is False
    assert SchedulingHandler._looks_like_reminder_task_followup("call John") is True


@pytest.mark.asyncio
async def test_handle_message_chat_contract_returns_agent_response():
    orchestrator = AgentOrchestrator(MagicMock(), SimpleNamespace(smart_llm=None))
    orchestrator.enable_task_pipeline = False
    orchestrator._handle_chat_response = AsyncMock(return_value=_response("hello"))

    response = await orchestrator.handle_message("hello", user_id="u1")

    assert isinstance(response, AgentResponse)
    assert response.display_text == "hello"
    orchestrator._handle_chat_response.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_message_task_contract_returns_agent_response():
    orchestrator = AgentOrchestrator(MagicMock(), SimpleNamespace(smart_llm=None))
    orchestrator.task_store.get_active_tasks = AsyncMock(return_value=[])
    orchestrator._handle_task_request = AsyncMock(return_value=_response("task created"))

    response = await orchestrator.handle_message("create task to plan trip", user_id="u1")

    assert isinstance(response, AgentResponse)
    assert "task created" in response.display_text
    orchestrator._handle_task_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_research_handler_returns_silent_ack_and_spawns_background_task():
    owner = MagicMock()
    owner._handoff_manager.delegate = AsyncMock(
        return_value=SimpleNamespace(status="accepted", structured_payload=None, error_code=None, user_visible_text="")
    )
    owner._consume_handoff_signal.return_value = "research"
    owner._build_handoff_request.return_value = SimpleNamespace(trace_id="trace-1")
    owner._extract_user_message_segment.return_value = None
    owner._current_session_id = "sess-1"
    owner._session = None
    owner.session = None
    owner._spawn_background_task = MagicMock(side_effect=lambda coro: coro.close())
    owner._append_conversation_history = MagicMock()

    handler = ResearchHandler(owner=owner)
    room = MagicMock()
    publish_agent_thinking = AsyncMock()
    publish_tool_execution = AsyncMock()

    response = await handler.handle_research_route(
        message="who is the CEO of Microsoft",
        user_id="u1",
        tool_context=SimpleNamespace(session_id="sess-1", trace_id="trace-1", room=room, task_id=None, conversation_id=None),
        publish_agent_thinking_fn=publish_agent_thinking,
        publish_tool_execution_fn=publish_tool_execution,
    )

    assert isinstance(response, AgentResponse)
    assert response.structured_data["_routing_mode_type"] == "research_pending"
    owner._spawn_background_task.assert_called_once()
    publish_agent_thinking.assert_awaited_once()
    publish_tool_execution.assert_awaited_once()


@pytest.mark.asyncio
async def test_media_handler_calls_handoff_manager_and_returns_agent_response():
    owner = MagicMock()
    owner._resolve_media_query_from_preferences = AsyncMock(return_value="play lofi")
    owner._consume_handoff_signal.return_value = "media"
    owner._build_handoff_request.return_value = SimpleNamespace(trace_id="trace-1")
    owner._handoff_manager.delegate = AsyncMock(
        return_value=SimpleNamespace(
            status="completed",
            structured_payload={"action": "play", "provider": "spotify", "success": True},
            user_visible_text="Playing on Spotify",
            error_code=None,
        )
    )
    owner._tag_response_with_routing_type.side_effect = lambda response, _kind: response
    owner.turn_state = {}

    handler = MediaHandler(owner=owner)
    response = await handler.handle_media_route(
        message="play some music",
        user_id="u1",
        tool_context=SimpleNamespace(session_id="sess-1", trace_id="trace-1"),
    )

    assert isinstance(response, AgentResponse)
    assert response.display_text == "Playing on Spotify"
    owner._handoff_manager.delegate.assert_awaited_once()


@pytest.mark.asyncio
async def test_scheduling_handler_followup_returns_agent_response():
    owner = MagicMock()
    owner._consume_handoff_signal.return_value = "scheduling"
    owner._build_handoff_request.return_value = SimpleNamespace(trace_id="trace-1")
    owner._handoff_manager.delegate = AsyncMock(
        return_value=SimpleNamespace(
            status="needs_followup",
            structured_payload={"clarification": "When would you like to be reminded?"},
            user_visible_text="",
            error_code=None,
        )
    )
    owner._tag_response_with_routing_type.side_effect = lambda response, _kind: response

    handler = SchedulingHandler(owner=owner)
    response = await handler.handle_scheduling_route(
        message="set a reminder",
        user_id="u1",
        tool_context=SimpleNamespace(trace_id="trace-1"),
    )

    assert isinstance(response, AgentResponse)
    assert "When would you like to be reminded?" in response.display_text


@pytest.mark.asyncio
async def test_scheduling_handler_missing_task_followup_writes_pending_state():
    owner = MagicMock()
    owner._action_state_enabled = True
    owner._consume_handoff_signal.return_value = "scheduling"
    owner._build_handoff_request.return_value = SimpleNamespace(trace_id="trace-1")
    owner._handoff_manager.delegate = AsyncMock(
        return_value=SimpleNamespace(
            status="needs_followup",
            structured_payload={
                "action_type": "set_reminder",
                "missing_slot": "task",
                "parameters": {"time": "tomorrow"},
                "clarification": "What should I remind you about?",
            },
            user_visible_text="",
            error_code=None,
        )
    )
    owner._session_key_for_context.return_value = "sess-1"
    owner._current_action_state_turn.return_value = 2
    owner._set_pending_scheduling_action_for_context.return_value = True
    owner._tag_response_with_routing_type.side_effect = lambda response, _kind: response

    handler = SchedulingHandler(owner=owner)
    response = await handler.handle_scheduling_route(
        message="set a reminder for tomorrow",
        user_id="u1",
        tool_context=SimpleNamespace(trace_id="trace-1"),
    )

    assert isinstance(response, AgentResponse)
    assert "What should I remind you about?" in response.display_text
    owner._set_pending_scheduling_action_for_context.assert_called_once()


@pytest.mark.asyncio
async def test_scheduling_handler_resumes_pending_task_followup():
    owner = MagicMock()
    owner._action_state_enabled = True
    owner._consume_handoff_signal.return_value = "scheduling"
    owner._build_handoff_request.return_value = SimpleNamespace(trace_id="trace-1")
    owner._handoff_manager.delegate = AsyncMock(
        return_value=SimpleNamespace(
            status="completed",
            structured_payload={
                "action_type": "set_reminder",
                "tool_name": "set_reminder",
                "parameters": {"text": "call John", "time": "tomorrow"},
                "confirmation_text": "I've set a reminder to call John tomorrow.",
            },
            user_visible_text="I've set a reminder to call John tomorrow.",
            error_code=None,
        )
    )
    owner._get_pending_scheduling_action_with_reason_for_context.return_value = (
        {"type": "set_reminder", "data": {"time": "tomorrow"}},
        "active",
    )
    owner._execute_tool_call = AsyncMock(
        return_value=(
            {"message": "I've set a reminder to call John tomorrow."},
            SimpleNamespace(status="success"),
        )
    )
    owner._set_last_action_for_context.return_value = True
    owner._clear_pending_scheduling_action_for_context.return_value = True
    owner._session_key_for_context.return_value = "sess-1"
    owner._current_action_state_turn.return_value = 3
    owner._tag_response_with_routing_type.side_effect = lambda response, _kind: response
    owner.turn_state = {}

    handler = SchedulingHandler(owner=owner)
    response = await handler.handle_scheduling_route(
        message="call John",
        user_id="u1",
        tool_context=SimpleNamespace(trace_id="trace-1"),
    )

    assert isinstance(response, AgentResponse)
    assert "set a reminder" in response.display_text.lower()
    kwargs = owner._build_handoff_request.call_args.kwargs
    assert kwargs["message"] == "set a reminder to call John tomorrow"
    owner._clear_pending_scheduling_action_for_context.assert_called()


@pytest.mark.asyncio
async def test_orchestrator_research_wrapper_delegates_flags():
    orchestrator = object.__new__(AgentOrchestrator)
    expected = _response("ok")
    recorder = _AsyncCallRecorder(expected)
    fake_handler = SimpleNamespace(handle_research_route=recorder)
    orchestrator._research_handler = fake_handler
    tool_context = SimpleNamespace()

    response = await orchestrator._handle_research_route(
        message="who is satya nadella",
        user_id="u1",
        tool_context=tool_context,
        query_rewritten=True,
        query_ambiguous=False,
    )

    assert response is expected
    assert len(recorder.calls) == 1
    kwargs = recorder.calls[0]
    assert kwargs["query_rewritten"] is True
    assert kwargs["query_ambiguous"] is False


@pytest.mark.asyncio
async def test_orchestrator_media_wrapper_delegates_args():
    orchestrator = object.__new__(AgentOrchestrator)
    expected = _response("ok")
    recorder = _AsyncCallRecorder(expected)
    fake_handler = SimpleNamespace(handle_media_route=recorder)
    orchestrator._media_handler = fake_handler
    tool_context = SimpleNamespace()

    response = await orchestrator._handle_media_route(
        message="play jazz",
        user_id="u1",
        tool_context=tool_context,
    )

    assert response is expected
    assert recorder.calls == [{
        "message": "play jazz",
        "user_id": "u1",
        "tool_context": tool_context,
    }]


@pytest.mark.asyncio
async def test_orchestrator_scheduling_wrapper_delegates_args():
    orchestrator = object.__new__(AgentOrchestrator)
    expected = _response("ok")
    recorder = _AsyncCallRecorder(expected)
    fake_handler = SimpleNamespace(handle_scheduling_route=recorder)
    orchestrator._scheduling_handler = fake_handler
    tool_context = SimpleNamespace()

    response = await orchestrator._handle_scheduling_route(
        message="set reminder tomorrow",
        user_id="u1",
        tool_context=tool_context,
    )

    assert response is expected
    assert recorder.calls == [{
        "message": "set reminder tomorrow",
        "user_id": "u1",
        "tool_context": tool_context,
    }]


@pytest.mark.asyncio
async def test_handle_message_onboarding_capture_continues_to_chat():
    orchestrator = AgentOrchestrator(MagicMock(), SimpleNamespace(smart_llm=None))
    orchestrator.enable_task_pipeline = False
    pref_manager = MagicMock()
    pref_manager.get_all = AsyncMock(return_value={})
    pref_manager.set = AsyncMock()
    orchestrator._preference_manager = pref_manager
    orchestrator.preference_manager = pref_manager
    orchestrator._handle_chat_response = AsyncMock(return_value=_response("captured"))

    response = await orchestrator.handle_message(
        "I use Spotify and I'm based in Hyderabad",
        user_id="u1",
    )

    assert isinstance(response, AgentResponse)
    assert response.display_text == "captured"
    assert pref_manager.set.await_count == 2


@pytest.mark.asyncio
async def test_handle_message_onboarding_prompt_needed_continues_to_chat():
    orchestrator = AgentOrchestrator(MagicMock(), SimpleNamespace(smart_llm=None))
    orchestrator.enable_task_pipeline = False
    pref_manager = MagicMock()
    pref_manager.get_all = AsyncMock(return_value={})
    pref_manager.set = AsyncMock()
    orchestrator._preference_manager = pref_manager
    orchestrator.preference_manager = pref_manager
    orchestrator._handle_chat_response = AsyncMock(return_value=_response("hello"))

    response = await orchestrator.handle_message("hello", user_id="u1")

    assert isinstance(response, AgentResponse)
    assert response.display_text == "hello"
    pref_manager.set.assert_not_awaited()
