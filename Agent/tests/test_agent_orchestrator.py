
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from types import SimpleNamespace
from core.orchestrator.agent_orchestrator import AgentOrchestrator
from core.tasks.task_models import TaskStep
from core.response.agent_response import AgentResponse, ToolInvocation
from core.research.research_models import ResearchResult, SourceItem
from core.media.media_models import MediaResult, MediaTrack
from core.system.system_models import SystemActionType, SystemResult
from core.governance.types import UserRole

@pytest.fixture
def mock_deps():
    with patch("core.orchestrator.agent_orchestrator.PlanningEngine") as MockPlanner, \
         patch("core.orchestrator.agent_orchestrator.TaskStore") as MockStore:
        
        # Setup Planner mock
        planner = MockPlanner.return_value
        planner.generate_plan = AsyncMock()
        
        # Setup Store mock
        store = MockStore.return_value
        store.create_task = AsyncMock(return_value=True)
        
        yield planner, store

@pytest.mark.asyncio
async def test_handle_intent_creates_task(mock_deps):
    mock_planner, mock_store = mock_deps
    
    # Mock plan
    mock_planner.generate_plan.return_value = [
        TaskStep(description="Step 1", worker="general")
    ]
    
    # Mock Agent
    mock_agent = MagicMock()
    mock_agent.user_id = "test_user"
    mock_agent.smart_llm = None
    
    # Init Orchestrator
    # Note: ctx is mocked
    orchestrator = AgentOrchestrator(MagicMock(), mock_agent)
    orchestrator._ensure_task_worker = AsyncMock()
    
    # Run
    response = await orchestrator.handle_message(
        "Create a task to plan weekly goals",
        user_id="test_user",
    )
    
    # Verify
    mock_planner.generate_plan.assert_called_once()
    planner_prompt = mock_planner.generate_plan.await_args.args[0]
    assert "Host Capability Profile:" in planner_prompt
    assert planner_prompt.endswith("Create a task to plan weekly goals")
    mock_store.create_task.assert_called_once()
    assert "started a task" in response.display_text

@pytest.mark.asyncio
async def test_handle_intent_fails_planning(mock_deps):
    mock_planner, mock_store = mock_deps
    
    # Mock empty plan
    mock_planner.generate_plan.return_value = []
    
    mock_agent = MagicMock()
    mock_agent.smart_llm = None
    orchestrator = AgentOrchestrator(MagicMock(), mock_agent)
    response = await orchestrator.handle_message("Create task: impossible", user_id="test_user")
    
    assert "couldn't create a plan" in response.display_text
    mock_store.create_task.assert_not_called()


@pytest.mark.asyncio
async def test_handle_intent_deprecation_routes_to_handle_message(mock_deps):
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator.handle_message = AsyncMock(return_value="ok")
    response = await orchestrator.handle_intent("hello", user_id="u1")
    assert response == "ok"
    orchestrator.handle_message.assert_called_once_with("hello", "u1")


def test_orchestrator_set_session_idempotent(caplog):
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    session = MagicMock()

    with caplog.at_level("INFO"):
        orchestrator.set_session(session)
        orchestrator.set_session(session)

    assert orchestrator.session is session
    assert orchestrator._attached_session_identity == str(id(session))
    assert "ORCHESTRATOR_SESSION_ATTACH_SKIPPED_SAME_SESSION" in caplog.text


class _EmptyStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_tool_synthesis_uses_toolless_explicit_mode():
    agent = MagicMock()
    agent.smart_llm = None
    orchestrator = AgentOrchestrator(MagicMock(), agent)
    role_llm = MagicMock()
    role_llm.chat = AsyncMock(return_value=_EmptyStream())

    tool_invocation = ToolInvocation(tool_name="get_current_datetime", status="success", latency_ms=1)
    await orchestrator._synthesize_tool_response(
        role_llm=role_llm,
        user_message="what time is it",
        tool_name="get_current_datetime",
        tool_output={"result": "time value"},
        tool_invocation=tool_invocation,
        mode="normal",
    )

    assert role_llm.chat.await_count >= 1
    for call in role_llm.chat.await_args_list:
        assert call.kwargs.get("tool_choice") == "none"


def test_synthesis_timeout_env_var_wired_on_init(monkeypatch):
    monkeypatch.setenv("VOICE_SYNTHESIS_TIMEOUT_S", "0.2")
    monkeypatch.setenv("SYNTHESIS_FALLBACK_WINDOW_SIZE", "12")
    monkeypatch.setenv("SYNTHESIS_FALLBACK_WARN_RATE", "0.25")
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    assert orchestrator._synthesis_timeout_s == pytest.approx(0.2)
    assert orchestrator._synthesis_fallback_window_size == 12
    assert orchestrator._synthesis_fallback_warn_rate == pytest.approx(0.25)


def test_voice_planner_tools_include_take_screenshot():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    assert "take_screenshot" in orchestrator._voice_planner_tools


@pytest.mark.asyncio
async def test_synthesis_timeout_uses_template_fallback():
    agent = MagicMock()
    agent.smart_llm = None
    orchestrator = AgentOrchestrator(MagicMock(), agent)
    orchestrator._run_theless_synthesis_with_timeout = AsyncMock(return_value=("", "timeout"))
    role_llm = MagicMock()
    role_llm.chat = AsyncMock(return_value=_EmptyStream())

    response = await orchestrator._synthesize_tool_response(
        role_llm=role_llm,
        user_message="open youtube",
        tool_name="open_app",
        tool_output={"app_name": "youtube"},
        tool_invocation=ToolInvocation(tool_name="open_app", status="success", latency_ms=2),
        mode="direct",
    )

    assert "Opened youtube." in response.display_text
    assert "{" not in response.voice_text
    assert "}" not in response.voice_text


def test_fallback_rate_counter_updates_and_warns(caplog):
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._synthesis_fallback_warn_rate = 0.2
    with caplog.at_level("WARNING"):
        orchestrator._record_synthesis_metrics(
            synthesis_status="timeout",
            fallback_used=True,
            fallback_source="tool_template",
            tool_name="open_app",
            mode="direct",
        )
        orchestrator._record_synthesis_metrics(
            synthesis_status="ok",
            fallback_used=False,
            fallback_source="none",
            tool_name="open_app",
            mode="direct",
        )

    assert orchestrator._synthesis_total == 2
    assert orchestrator._synthesis_timeout_total == 1
    assert orchestrator._synthesis_fallback_total == 1
    assert "SYNTHESIS_FALLBACK_RATE_HIGH" in caplog.text


@pytest.mark.asyncio
async def test_execute_tool_call_exception_returns_structured_failure_payload():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    mock_router = MagicMock()
    mock_router.tool_executor = AsyncMock(side_effect=RuntimeError("Traceback: boom"))

    with patch("core.orchestrator.agent_orchestrator.get_router", return_value=mock_router):
        result, invocation = await orchestrator._execute_tool_call(
            tool_name="web_search",
            args={"query": "x"},
            user_id="u1",
        )

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["message"] == "I was unable to complete that."
    assert "traceback" not in result["message"].lower()
    assert invocation.status == "failed"


@pytest.mark.asyncio
async def test_execute_tool_call_normalizes_error_like_text_to_safe_message():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    mock_router = MagicMock()
    mock_router.tool_executor = AsyncMock(return_value="Error executing command: Traceback ...")

    with patch("core.orchestrator.agent_orchestrator.get_router", return_value=mock_router):
        result, invocation = await orchestrator._execute_tool_call(
            tool_name="run_shell_command",
            args={"command": "bad"},
            user_id="u1",
        )

    assert result["success"] is False
    assert result["message"] == "I was unable to complete that."
    assert invocation.status == "failed"


@pytest.mark.asyncio
async def test_fastpath_tool_failure_does_not_expose_exception_text():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._execute_tool_call = AsyncMock(
        return_value=(
            {
                "success": False,
                "message": "I was unable to complete that.",
                "error_code": "tool_exception",
            },
            ToolInvocation(tool_name="open_app", status="failed"),
        )
    )

    response = await orchestrator._handle_chat_response(
        "open youtube",
        user_id="u1",
        origin="chat",
    )

    assert "traceback" not in response.display_text.lower()
    assert "traceback" not in response.voice_text.lower()
    assert "unable to complete" in response.voice_text.lower()


@pytest.mark.asyncio
async def test_fastpath_precedence_over_research_route():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._execute_tool_call = AsyncMock(
        return_value=(
            {"result": "10:00 AM"},
            ToolInvocation(tool_name="get_time", status="success", latency_ms=1),
        )
    )
    orchestrator._run_inline_research_pipeline = AsyncMock(side_effect=AssertionError("research should not run"))

    response = await orchestrator._handle_chat_response(
        "what time is it",
        user_id="u1",
        origin="chat",
    )

    assert "time" in response.voice_text.lower()
    assert orchestrator._run_inline_research_pipeline.await_count == 0


@pytest.mark.asyncio
async def test_research_query_routes_to_research_pipeline():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="research")
    orchestrator._run_inline_research_pipeline = AsyncMock(
        return_value=ResearchResult(
            summary="Here are the latest AI highlights.",
            voice_summary="Short spoken summary.",
            sources=[
                SourceItem.from_values(
                    title="Source A",
                    url="https://example.com/a",
                    snippet="Snippet A",
                    provider="tavily",
                )
            ],
            query="search for latest ai news",
            trace_id="trace-1",
            duration_ms=42,
        )
    )

    response = await orchestrator._handle_chat_response(
        "what's happening with tesla stock and recent news",
        user_id="u1",
        origin="chat",
    )

    # Response is metadata-only silent ack; research runs in background
    assert response.display_text == ""
    assert response.voice_text == ""
    assert response.structured_data is not None
    assert "_routing_mode_type" in response.structured_data
    assert response.structured_data["_routing_mode_type"] == "research_pending"
    assert response.structured_data["_interaction_mode"] == "silent_ack"
    assert response.structured_data["_suppress_assistant_output"] is True
    assert "turn_id" in response.structured_data
    # Inline pipeline is invoked by background task after ack returns.


@pytest.mark.asyncio
async def test_research_route_publishes_searching_and_tool_started_for_live_room():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="research")
    tool_context = SimpleNamespace(
        session_id="voice-session-live",
        trace_id="trace-live",
        room=MagicMock(),
        conversation_id="conversation-42",
        task_id="task-42",
    )

    with patch("core.orchestrator.agent_orchestrator.publish_agent_thinking", new=AsyncMock()) as publish_thinking, \
         patch("core.orchestrator.agent_orchestrator.publish_tool_execution", new=AsyncMock()) as publish_tool, \
         patch("core.orchestrator.agent_orchestrator.asyncio.create_task") as create_task:
        create_task.return_value = MagicMock()

        response = await orchestrator._handle_research_route(
            message="search for the latest AI news",
            user_id="u1",
            tool_context=tool_context,
        )

    assert response.structured_data is not None
    publish_thinking.assert_awaited_once()
    publish_tool.assert_awaited_once()
    thinking_args = publish_thinking.await_args.args
    assert thinking_args[0] is tool_context.room
    assert thinking_args[2] == "searching"
    tool_kwargs = publish_tool.await_args.kwargs
    assert tool_kwargs["message"] == "Searching the web for research context."
    assert tool_kwargs["task_id"] == "task-42"
    assert tool_kwargs["conversation_id"] == "conversation-42"
    create_task.assert_called_once()


@pytest.mark.asyncio
async def test_search_for_routes_to_research_pipeline_not_fastpath():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="research")
    orchestrator._execute_tool_call = AsyncMock(side_effect=AssertionError("fast-path should not run"))
    orchestrator._run_inline_research_pipeline = AsyncMock(
        return_value=ResearchResult(
            summary="Research summary for AI agents.",
            voice_summary="One sentence voice summary.",
            sources=[
                SourceItem.from_values(
                    title="AI Source",
                    url="https://example.com/ai",
                    snippet="AI snippet",
                    provider="tavily",
                )
            ],
            query="search for latest developments in ai agents",
            trace_id="trace-search-for",
            duration_ms=35,
        )
    )

    response = await orchestrator._handle_chat_response(
        "search for latest developments in AI agents",
        user_id="u1",
        origin="chat",
    )

    # Response is metadata-only silent ack; research runs in background
    assert response.display_text == ""
    assert response.voice_text == ""
    assert response.structured_data is not None
    assert "_routing_mode_type" in response.structured_data
    assert response.structured_data["_routing_mode_type"] == "research_pending"
    assert response.structured_data["_interaction_mode"] == "silent_ack"
    assert response.structured_data["_suppress_assistant_output"] is True
    assert "turn_id" in response.structured_data
    # Tool call should not be invoked for research routing
    assert orchestrator._execute_tool_call.await_count == 0


@pytest.mark.asyncio
async def test_research_background_uses_inline_pipeline_runtime_cutover():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._run_inline_research_pipeline = AsyncMock(
        return_value=ResearchResult(
            summary="Inline research summary.",
            voice_summary="Inline voice summary.",
            sources=[
                SourceItem.from_values(
                    title="S1",
                    url="https://example.com/inline",
                    snippet="inline snippet",
                    provider="tavily",
                )
            ],
            query="who is the ceo of openai",
            trace_id="trace-inline",
            duration_ms=15,
        )
    )

    await orchestrator._run_research_background(
        query="who is the ceo of openai",
        user_id="u1",
        session_id="voice-session-inline",
        trace_id="trace-inline",
        turn_id="turn-inline",
        room=None,
        session=None,
    )

    assert orchestrator._run_inline_research_pipeline.await_count == 1
    kwargs = orchestrator._run_inline_research_pipeline.await_args.kwargs
    assert kwargs["query"] == "who is the ceo of openai"
    assert kwargs["session_id"] == "voice-session-inline"


def test_research_query_rewrite_resolves_pronoun_from_recent_history():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._conversation_history = [
        {"role": "user", "content": "Who is the prime minister of India?", "source": "history"},
        {"role": "assistant", "content": "The prime minister of India is Narendra Modi.", "source": "history"},
    ]

    rewritten, changed, ambiguous = orchestrator.rewrite_research_query_for_context(
        "tell me about him",
        tool_context=SimpleNamespace(session_id="voice-session-1"),
    )

    assert changed is True
    assert ambiguous is False
    assert "him" not in rewritten.lower()
    assert "prime minister of India" in rewritten or "Narendra Modi" in rewritten


@pytest.mark.asyncio
async def test_research_completion_stores_context_and_history_summary():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._run_inline_research_pipeline = AsyncMock(
        return_value=ResearchResult(
            summary="Narendra Modi is the prime minister of India and has served since 2014.",
            voice_summary="Narendra Modi is the prime minister of India and has served since 2014.",
            sources=[
                SourceItem.from_values(
                    title="Source A",
                    url="https://example.com/a",
                    snippet="Snippet A",
                    provider="tavily",
                )
            ],
            query="Who is the prime minister of India?",
            trace_id="trace-ctx",
            duration_ms=12,
        )
    )

    await orchestrator._run_research_background(
        query="Who is the prime minister of India?",
        user_id="u1",
        session_id="voice-session-ctx",
        trace_id="trace-ctx",
        turn_id="turn-ctx",
        room=None,
        session=None,
    )

    assert "voice-session-ctx" in orchestrator._last_research_contexts
    stored = orchestrator._last_research_contexts["voice-session-ctx"]
    assert "prime minister" in str(stored.get("subject") or "").lower() or "modi" in str(stored.get("subject") or "").lower()
    assert any(item.get("source") == "research_summary" for item in orchestrator._conversation_history)


@pytest.mark.asyncio
async def test_research_background_publishes_tool_finished_and_result():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._run_inline_research_pipeline = AsyncMock(
        return_value=ResearchResult(
            summary="Research summary.",
            voice_summary="Research voice summary.",
            sources=[
                SourceItem.from_values(
                    title="Source A",
                    url="https://example.com/a",
                    snippet="Snippet A",
                    provider="tavily",
                )
            ],
            query="latest ai news",
            trace_id="trace-finished",
            duration_ms=12,
        )
    )

    with patch("core.orchestrator.agent_orchestrator.publish_tool_execution", new=AsyncMock()) as publish_tool, \
         patch("core.communication.publish_research_result", new=AsyncMock()) as publish_result:
        await orchestrator._run_research_background(
            query="latest ai news",
            user_id="u1",
            session_id="voice-session-finished",
            trace_id="trace-finished",
            turn_id="turn-finished",
            room=MagicMock(),
            session=None,
            task_id="task-finished",
            conversation_id="conversation-finished",
        )

    publish_tool.assert_awaited_once()
    tool_args = publish_tool.await_args.args
    assert tool_args[2] == "web_search"
    assert tool_args[3] == "finished"
    tool_kwargs = publish_tool.await_args.kwargs
    assert tool_kwargs["task_id"] == "task-finished"
    assert tool_kwargs["conversation_id"] == "conversation-finished"
    publish_result.assert_awaited_once()
    result_kwargs = publish_result.await_args.kwargs
    assert result_kwargs["task_id"] == "task-finished"
    assert result_kwargs["conversation_id"] == "conversation-finished"


@pytest.mark.asyncio
async def test_pronoun_followup_forces_research_with_rewrite():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="chat")
    orchestrator._last_research_contexts["voice-session-1"] = {
        "subject": "Narendra Modi",
        "query": "Who is the prime minister of India?",
        "summary_sentence": "Narendra Modi is the prime minister of India.",
        "updated_at": 0.0,
        "expires_at": 9999999999.0,
    }
    orchestrator._handle_research_route = AsyncMock(
        return_value=AgentResponse(
            display_text="",
            voice_text="",
            structured_data={
                "_routing_mode_type": "research_pending",
                "_interaction_mode": "silent_ack",
                "_suppress_assistant_output": True,
            },
        )
    )

    response = await orchestrator._handle_chat_response(
        "tell me more about him",
        user_id="u1",
        tool_context=SimpleNamespace(session_id="voice-session-1"),
        origin="voice",
    )

    assert response.display_text == ""
    assert response.voice_text == ""
    assert response.structured_data["_suppress_assistant_output"] is True
    assert orchestrator._router.route.await_count == 0
    assert orchestrator._handle_research_route.await_count == 1
    rewritten_message = orchestrator._handle_research_route.await_args.kwargs["message"]
    assert "him" not in rewritten_message.lower()
    assert "narendra modi" in rewritten_message.lower()


@pytest.mark.asyncio
async def test_router_not_called_when_pronoun_override_forces_research():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="chat")
    orchestrator._last_research_contexts["voice-session-2"] = {
        "subject": "Sam Altman",
        "query": "Who is the CEO of OpenAI?",
        "summary_sentence": "Sam Altman is the CEO of OpenAI.",
        "updated_at": 0.0,
        "expires_at": 9999999999.0,
    }
    orchestrator._handle_research_route = AsyncMock(
        return_value=AgentResponse(
            display_text="",
            voice_text="",
            structured_data={
                "_routing_mode_type": "research_pending",
                "_interaction_mode": "silent_ack",
                "_suppress_assistant_output": True,
            },
        )
    )

    await orchestrator._handle_chat_response(
        "what does he do exactly",
        user_id="u1",
        tool_context=SimpleNamespace(session_id="voice-session-2"),
        origin="voice",
    )

    assert orchestrator._handle_research_route.await_count == 1
    assert orchestrator._router.route.await_count == 0


@pytest.mark.asyncio
async def test_research_context_ttl_expiry_disables_override():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._last_research_contexts["voice-session-3"] = {
        "subject": "Narendra Modi",
        "query": "Who is the prime minister of India?",
        "summary_sentence": "Narendra Modi is the prime minister of India.",
        "updated_at": 0.0,
        "expires_at": 1.0,
    }
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="identity")
    orchestrator._handle_research_route = AsyncMock(side_effect=AssertionError("research route should not run"))

    response = await orchestrator._handle_chat_response(
        "tell me more about him",
        user_id="u1",
        tool_context=SimpleNamespace(session_id="voice-session-3"),
        origin="voice",
    )

    assert "clarify who you mean" in response.display_text.lower()
    assert orchestrator._router.route.await_count == 0
    assert orchestrator._handle_research_route.await_count == 0


@pytest.mark.asyncio
async def test_research_query_ambiguous_prompts_clarification_not_research():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="research")
    orchestrator._handle_research_route = AsyncMock(side_effect=AssertionError("research route should not run"))

    response = await orchestrator._handle_chat_response(
        "tell me about him",
        user_id="u1",
        origin="chat",
    )

    assert "clarify who you mean" in response.display_text.lower()
    assert orchestrator._router.route.await_count == 0
    assert orchestrator._handle_research_route.await_count == 0


@pytest.mark.asyncio
async def test_research_voice_tts_sanitization_filters_json_fragment_before_session_say():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._run_inline_research_pipeline = AsyncMock(
        return_value=ResearchResult(
            summary='**Current Prime Minister**\n🔹 Narendra Modi is the prime minister of India.\nSources: [1]',
            voice_summary='Current Prime Minister of India "display": Current Prime Minister of India, "voice": "The current prime minister of India is Narendra Modi."',
            sources=[
                SourceItem.from_values(
                    title="Source A",
                    url="https://example.com/a",
                    snippet="Snippet A",
                    provider="tavily",
                )
            ],
            query="Who is the prime minister of India?",
            trace_id="trace-tts",
            duration_ms=10,
        )
    )
    session = SimpleNamespace(say=AsyncMock())

    await orchestrator._run_research_background(
        query="Who is the prime minister of India?",
        user_id="u1",
        session_id="voice-session-tts",
        trace_id="trace-tts",
        turn_id="turn-tts",
        room=None,
        session=session,
    )

    assert session.say.await_count == 1
    spoken_text = session.say.await_args.args[0]
    assert '"display":' not in spoken_text.lower()
    assert '"voice":' not in spoken_text.lower()
    assert "{" not in spoken_text
    assert "}" not in spoken_text


@pytest.mark.asyncio
async def test_fastpath_open_app_does_not_route_to_media_agent():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._execute_tool_call = AsyncMock(
        return_value=(
            {"success": True, "result": "Opened firefox"},
            ToolInvocation(tool_name="open_app", status="success", latency_ms=2),
        )
    )
    orchestrator._resolve_media_agent = MagicMock(side_effect=AssertionError("media should not run"))

    response = await orchestrator._handle_chat_response(
        "open firefox",
        user_id="u1",
        origin="chat",
    )

    assert "opening" in response.voice_text.lower() or "opened" in response.voice_text.lower()
    assert orchestrator._resolve_media_agent.call_count == 0


@pytest.mark.asyncio
async def test_media_query_routes_to_media_agent():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="media_play")
    orchestrator._handoff_manager = MagicMock()
    orchestrator._handoff_manager.consume_signal = MagicMock(return_value="media")
    orchestrator._handoff_manager.delegate = AsyncMock(
        return_value=SimpleNamespace(
            status="completed",
            user_visible_text="Now playing Song A by Artist A on Spotify.",
            structured_payload={
                "action": "play",
                "provider": "spotify",
                "track_name": "Song A",
                "artist": "Artist A",
                "album_art_url": "",
                "track_url": "https://open.spotify.com/track/abc",
                "trace_id": "trace-media",
                "success": True,
                "message": "Now playing Song A by Artist A on Spotify.",
            },
        )
    )

    response = await orchestrator._handle_chat_response(
        "play song a on spotify",
        user_id="u1",
        origin="chat",
    )

    orchestrator._handoff_manager.delegate.assert_awaited_once()
    assert "spotify" in response.display_text.lower()
    assert response.structured_data is not None
    assert "_media_result" in response.structured_data


def test_report_export_intent_detection_keywords():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    assert orchestrator._is_report_export_request(
        "search the web and export report and save it in my downloads"
    )
    assert not orchestrator._is_report_export_request(
        "give me an in-depth report on the latest iran war developments"
    )


@pytest.mark.asyncio
async def test_report_export_requires_trusted_role():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())

    response_text = await orchestrator._try_handle_report_export_task(
        user_text="make a full report and save it in my downloads",
        user_id="u1",
        tool_context=SimpleNamespace(user_role=UserRole.USER),
    )

    assert response_text is not None
    assert "trusted role" in response_text.lower()


@pytest.mark.asyncio
async def test_report_export_trusted_role_creates_docx():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._run_inline_research_pipeline = AsyncMock(
        return_value=ResearchResult(
            summary="Detailed research summary.",
            voice_summary="Detailed voice summary.",
            sources=[
                SourceItem.from_values(
                    title="Source A",
                    url="https://example.com/source-a",
                    snippet="Snippet A",
                    provider="tavily",
                )
            ],
            query="iran and us conflict market report",
            trace_id="trace-report",
            duration_ms=20,
            voice_mode="deep",
        )
    )
    orchestrator._execute_tool_call = AsyncMock(
        return_value=(
            {"success": True, "message": "Created Word document"},
            ToolInvocation(tool_name="create_docx", status="success", latency_ms=4),
        )
    )

    response_text = await orchestrator._try_handle_report_export_task(
        user_text="create a detailed report and save it to my downloads",
        user_id="u1",
        tool_context=SimpleNamespace(user_role=UserRole.TRUSTED, session_id="s1", trace_id="t1"),
    )

    assert response_text is not None
    assert "saved it to ~/Downloads/" in response_text
    assert orchestrator._execute_tool_call.await_count == 1
    tool_name = orchestrator._execute_tool_call.await_args.args[0]
    payload = orchestrator._execute_tool_call.await_args.args[1]
    assert tool_name == "create_docx"
    assert payload["path"].startswith("~/Downloads/")


@pytest.mark.asyncio
async def test_system_routing_uses_router_decision():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="system")
    fake_system_agent = MagicMock()
    fake_system_agent.run = AsyncMock(
        return_value=SystemResult(
            success=True,
            action_type=SystemActionType.FILE_DELETE,
            message="Action cancelled.",
            detail="",
            rollback_available=False,
            trace_id="trace-system-route",
        )
    )
    orchestrator._resolve_system_agent = MagicMock(return_value=fake_system_agent)

    response = await orchestrator._handle_chat_response(
        "delete the file test.txt",
        user_id="u1",
        origin="chat",
    )

    assert response.display_text == "Action cancelled."
    orchestrator._router.route.assert_awaited_once()


@pytest.mark.asyncio
async def test_scheduling_route_uses_handoff_manager_and_executes_tool():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="scheduling")
    orchestrator._handoff_manager = MagicMock()
    orchestrator._handoff_manager.consume_signal = MagicMock(return_value="scheduling")
    orchestrator._handoff_manager.delegate = AsyncMock(
        return_value=SimpleNamespace(
            status="completed",
            user_visible_text="I've set a reminder to drink water in 20 minutes.",
            structured_payload={
                "action_type": "set_reminder",
                "tool_name": "set_reminder",
                "parameters": {"text": "drink water", "time": "in 20 minutes"},
                "confirmation_text": "I've set a reminder to drink water in 20 minutes.",
                "trace_id": "trace-scheduling",
            },
        )
    )
    orchestrator._execute_tool_call = AsyncMock(
        return_value=(
            {"success": True, "message": "Reminder set: 'drink water' for in 20 minutes."},
            SimpleNamespace(status="success"),
        )
    )

    response = await orchestrator._handle_chat_response(
        "set a reminder to drink water in 20 minutes",
        user_id="u1",
        origin="chat",
    )

    orchestrator._handoff_manager.delegate.assert_awaited_once()
    orchestrator._execute_tool_call.assert_awaited_once()
    assert "drink water" in response.display_text.lower()
    assert response.structured_data["_scheduling_result"]["tool_name"] == "set_reminder"


@pytest.mark.asyncio
async def test_scheduling_route_returns_followup_when_time_missing():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="scheduling")
    orchestrator._handoff_manager = MagicMock()
    orchestrator._handoff_manager.consume_signal = MagicMock(return_value="scheduling")
    orchestrator._handoff_manager.delegate = AsyncMock(
        return_value=SimpleNamespace(
            status="needs_followup",
            user_visible_text="When would you like to be reminded?",
            structured_payload={"clarification": "When would you like to be reminded?"},
        )
    )

    response = await orchestrator._handle_chat_response(
        "remind me to call John",
        user_id="u1",
        origin="chat",
    )

    assert response.display_text == "When would you like to be reminded?"
    assert response.structured_data["_scheduling_followup"]["clarification"] == "When would you like to be reminded?"


@pytest.mark.asyncio
async def test_system_query_routes_to_system_agent():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="system")
    fake_system_agent = MagicMock()
    fake_system_agent.run = AsyncMock(
        return_value=SystemResult(
            success=True,
            action_type=SystemActionType.SCREENSHOT,
            message="Saved screenshot.",
            detail="/tmp/maya_screen.png",
            rollback_available=False,
            trace_id="trace-system",
        )
    )
    orchestrator._resolve_system_agent = MagicMock(return_value=fake_system_agent)

    response = await orchestrator._handle_chat_response(
        "take a screenshot",
        user_id="u1",
        origin="chat",
    )

    assert response.display_text == "Saved screenshot."
    assert response.structured_data is not None
    assert response.structured_data["_system_result"]["action_type"] == "SCREENSHOT"
    fake_system_agent.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_lookup_profile_name_from_memory_prefers_metadata_value():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator.memory = SimpleNamespace(
        retrieve_relevant_memories_with_scope_fallback_async=AsyncMock(
            return_value=[
                {
                    "text": "User profile fact: name=Harsha",
                    "metadata": {
                        "memory_kind": "profile_fact",
                        "field": "name",
                        "value": "Harsha",
                    },
                }
            ]
        )
    )

    name = await orchestrator._lookup_profile_name_from_memory(
        user_id="u1",
        session_id="s1",
        origin="chat",
    )

    assert name == "Harsha"
