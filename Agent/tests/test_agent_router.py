import asyncio
import ast
import inspect
import json
import re
import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.agents.contracts import AgentHandoffResult
from core.orchestrator.agent_orchestrator import AgentOrchestrator
from core.orchestrator.agent_router import AgentRouter
from core.orchestrator.fast_path_router import FastPathRouter
from core.response.agent_response import ToolInvocation
from core.response.response_formatter import ResponseFormatter
from core.security.input_guard import InputGuard


class _MappingLLM:
    def __init__(self, mapping: dict[str, str], default: str = "chat") -> None:
        self._mapping = mapping
        self._default = default

    async def chat(self, prompt: str, max_tokens: int = 10, temperature: float = 0.0) -> str:
        del max_tokens, temperature

        # Handle FactClassifier prompt path.
        if "Answer:" in prompt and "USER MESSAGE:" not in prompt:
            fact_match = re.search(r"Question:\s*(.+?)(?:\nAnswer:)", prompt, re.IGNORECASE | re.DOTALL)
            if fact_match:
                utterance = fact_match.group(1).strip().lower()
                if any(k in utterance for k in ("current", "latest", "recent", "news")):
                    return "research"
                if any(
                    k in utterance
                    for k in (
                        "retrieval augmented generation",
                        "who made ",
                        "how does ",
                        "explain ",
                        "what are ",
                    )
                ):
                    return "research"
                if any(
                    k in utterance
                    for k in (
                        "prime minister",
                        "pm of",
                        "president of",
                        "ceo of",
                        "capital of",
                        "currency of",
                        "population of",
                        "how old is",
                        "how tall is",
                        "who founded",
                        "who runs",
                    )
                ):
                    return "fact"
                if utterance.startswith("what is "):
                    return "fact"
                return "research"

        match = re.search(r'USER MESSAGE: "(.*)"\n\nReply with ONLY one word:', prompt, re.DOTALL)
        utterance = match.group(1) if match else ""
        return self._mapping.get(utterance, self._default)


class _ShadowLLM:
    def __init__(self):
        self.prompts: list[str] = []

    async def chat(self, prompt: str, max_tokens: int = 10, temperature: float = 0.0) -> str:
        del max_tokens, temperature
        self.prompts.append(prompt)
        if "routing shadow evaluator" in prompt:
            return json.dumps(
                {
                    "type": "chat",
                    "target": "chat",
                    "tool": None,
                    "arguments": {},
                    "confidence": 0.82,
                    "reason": "small_talk",
                }
            )
        return "chat"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("utterance", "expected"),
    [
        ("what is your name", "identity"),
        ("who are you", "identity"),
        ("introduce yourself", "identity"),
        ("what can you do", "identity"),
        ("are you an AI", "identity"),
        ("play music", "media_play"),
        ("play songs by AR Rahman", "media_play"),
        ("put on some music", "media_play"),
        ("play hotel california", "media_play"),
        ("start playing", "media_play"),
        ("search for AI agent trends", "research"),
        ("what is retrieval augmented generation", "research"),
        ("tell me about DeepMind", "research"),
        ("who made Linux", "research"),
        ("news about foundation models", "research"),
        ("can you use web search or not", "research"),
        ("take a screenshot", "system"),
        ("take a photograph", "system"),
        ("open file report.txt", "system"),
        ("open browser and click settings", "system"),
        ("move folder downloads", "system"),
        ("close window", "system"),
        ("resize window", "system"),
        ("hello", "chat"),
        ("how are you", "chat"),
        ("tell me a joke", "chat"),
        ("2 plus 2", "chat"),
        ("thanks", "chat"),
    ],
)
async def test_agent_router_classifies_25_utterances(utterance: str, expected: str) -> None:
    router = AgentRouter(_MappingLLM({utterance: expected}))
    assert await router.route(utterance, "u1") == expected


@pytest.mark.asyncio
async def test_agent_router_depth_exceeded_returns_chat_and_resets_counter() -> None:
    llm = _MappingLLM({"hello": "identity"})
    router = AgentRouter(llm)
    router._depth["u1"] = router.MAX_DEPTH

    result = await router.route("hello", "u1")

    assert result == "chat"
    assert router._depth["u1"] == 0


@pytest.mark.asyncio
async def test_agent_router_llm_failure_returns_chat() -> None:
    class _FailLLM:
        async def chat(self, prompt: str, max_tokens: int = 10, temperature: float = 0.0) -> str:
            del prompt, max_tokens, temperature
            raise RuntimeError("boom")

    router = AgentRouter(_FailLLM())
    assert await router.route("tell me something interesting", "u1") == "chat"


@pytest.mark.asyncio
async def test_agent_router_small_talk_override_forces_chat() -> None:
    router = AgentRouter(_MappingLLM({"how are you": "identity"}))
    assert await router.route("how are you", "u1") == "chat"


@pytest.mark.asyncio
async def test_agent_router_short_followup_after_question_routes_to_chat() -> None:
    router = AgentRouter(_MappingLLM({"just a small one": "research"}))
    chat_ctx = [
        {"role": "assistant", "content": "What kind of app do you want?"},
        {"role": "user", "content": "I need an app"},
    ]

    result = await router.route("just a small one", "u1", chat_ctx=chat_ctx)

    assert result == "chat"


@pytest.mark.asyncio
async def test_agent_router_short_followup_without_question_uses_normal_routing() -> None:
    router = AgentRouter(_MappingLLM({"just a small one": "research"}))
    chat_ctx = [
        {"role": "assistant", "content": "I can help with that."},
        {"role": "user", "content": "I need an app"},
    ]

    result = await router.route("just a small one", "u1", chat_ctx=chat_ctx)

    assert result == "research"


@pytest.mark.asyncio
async def test_agent_router_context_followup_does_not_override_explicit_research_intent() -> None:
    router = AgentRouter(_MappingLLM({"search for house budget app": "chat"}))
    chat_ctx = [
        {"role": "assistant", "content": "Do you want me to look this up?"},
    ]

    result = await router.route("search for house budget app", "u1", chat_ctx=chat_ctx)

    assert result == "research"


@pytest.mark.asyncio
async def test_agent_router_context_followup_does_not_override_explicit_system_intent() -> None:
    router = AgentRouter(_MappingLLM({"open browser settings": "chat"}))
    chat_ctx = [
        {"role": "assistant", "content": "Do you want to continue?"},
    ]

    result = await router.route("open browser settings", "u1", chat_ctx=chat_ctx)

    assert result == "system"


@pytest.mark.asyncio
async def test_agent_router_ambiguous_followup_inherits_previous_route() -> None:
    router = AgentRouter(
        _MappingLLM(
            {
                "tell me about nvidia's latest earnings": "research",
                "what's the reason": "chat",
            }
        )
    )

    first = await router.route("tell me about nvidia's latest earnings", "u1")
    followup = await router.route("what's the reason", "u1")

    assert first == "research"
    assert followup == "research"


@pytest.mark.asyncio
async def test_agent_router_ambiguous_followup_does_not_override_explicit_direct_action() -> None:
    router = AgentRouter(
        _MappingLLM(
            {
                "tell me about cpu trends": "research",
                "next track": "chat",
            }
        )
    )
    await router.route("tell me about cpu trends", "u1")

    followup = await router.route("next track", "u1")

    assert followup == "media_play"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "utterance",
    [
        "next track",
        "next song",
        "next video",
    ],
)
async def test_agent_router_deterministic_media_next_controls(utterance: str) -> None:
    router = AgentRouter(_MappingLLM({}))
    assert await router.route(utterance, "u1") == "media_play"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "utterance",
    [
        "list my tasks",
        "show my tasks",
        "get my tasks",
        "my tasks",
    ],
)
async def test_agent_router_task_list_routes_to_chat_not_scheduling(utterance: str) -> None:
    router = AgentRouter(_MappingLLM({utterance: "scheduling"}))
    result = await router.route(utterance, "u1")
    assert result == "chat"
    assert result != "scheduling"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "utterance",
    [
        "what reminder did I set",
        "what's my reminder",
        "when is my reminder",
    ],
)
async def test_agent_router_routes_reminder_status_queries_to_scheduling(utterance: str) -> None:
    router = AgentRouter(_MappingLLM({utterance: "chat"}))
    result = await router.route(utterance, "u1")
    assert result == "scheduling"


def test_input_guard_sanitizes_and_truncates() -> None:
    raw = (("ab" * 5000) + "\x01\x02")
    cleaned = InputGuard.sanitize(raw)
    assert len(cleaned) == 4000
    assert "\x01" not in cleaned
    assert "\x02" not in cleaned


@pytest.mark.asyncio
async def test_empty_input_returns_safe_fallback_without_router_call() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="chat")

    response = await orchestrator._handle_chat_response("\x00\x01\x02   ", user_id="u1", origin="chat")

    assert response.display_text == "I didn't catch that."
    orchestrator._router.route.assert_not_awaited()


@pytest.mark.asyncio
async def test_long_input_is_truncated_before_routing() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="identity")
    orchestrator._handle_identity_fast_path = AsyncMock(
        return_value=ResponseFormatter.build_response("I am Maya.")
    )

    long_message = "abcd" * 3000
    await orchestrator._handle_chat_response(long_message, user_id="u1", origin="chat")

    routed_text = orchestrator._router.route.await_args.args[0]
    assert len(routed_text) == 4000


@pytest.mark.asyncio
async def test_next_track_uses_fast_path_and_skips_router() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="chat")
    orchestrator._execute_tool_call = AsyncMock(
        return_value=(
            {"success": True, "result": "Next track."},
            ToolInvocation(tool_name="run_shell_command", status="success", latency_ms=1),
        )
    )

    response = await orchestrator._handle_chat_response("next track", user_id="u1", origin="chat")

    assert "next" in response.voice_text.lower()
    orchestrator._router.route.assert_not_awaited()


@pytest.mark.asyncio
async def test_identity_routing_does_not_hit_research() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="identity")
    orchestrator._handle_identity_fast_path = AsyncMock(
        return_value=ResponseFormatter.build_response("I'm Maya.")
    )
    orchestrator._handle_research_route = AsyncMock(
        side_effect=AssertionError("research must not run")
    )

    response = await orchestrator._handle_chat_response("what is your name", user_id="u1", origin="chat")

    assert "maya" in response.display_text.lower()
    orchestrator._handle_identity_fast_path.assert_awaited_once()


@pytest.mark.asyncio
async def test_greeting_uses_small_talk_fast_path_without_router() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(
        side_effect=AssertionError("router must not run for greeting fast path")
    )

    response = await orchestrator._handle_chat_response("hello", user_id="u1", origin="chat")

    assert "maya" in response.display_text.lower()
    orchestrator._router.route.assert_not_awaited()


@pytest.mark.asyncio
async def test_voice_continuation_fragment_returns_clarification_and_skips_router() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator.agent.chat_ctx = SimpleNamespace(
        messages=[SimpleNamespace(role="assistant", content="What kind of app do you want?")]
    )
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(side_effect=AssertionError("router should not run"))

    response = await orchestrator._handle_chat_response(
        "just a small one",
        user_id="u1",
        origin="voice",
    )

    assert "please continue your request" in response.display_text.lower()
    orchestrator._router.route.assert_not_awaited()


@pytest.mark.asyncio
async def test_voice_short_command_allowlist_does_not_trigger_fragment_guard() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator.agent.chat_ctx = SimpleNamespace(
        messages=[SimpleNamespace(role="assistant", content="Do you want me to continue?")]
    )
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="identity")
    orchestrator._handle_identity_fast_path = AsyncMock(
        return_value=ResponseFormatter.build_response("I'm Maya.")
    )

    response = await orchestrator._handle_chat_response(
        "yes",
        user_id="u1",
        origin="voice",
    )

    assert "maya" in response.display_text.lower()
    orchestrator._router.route.assert_awaited_once()


@pytest.mark.asyncio
async def test_voice_research_route_is_demoted_for_three_word_query() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="research")
    orchestrator._handle_research_route = AsyncMock(
        side_effect=AssertionError("research should be demoted to chat")
    )
    orchestrator._is_phase6_context_builder_active = MagicMock(return_value=False)

    response = await orchestrator._handle_chat_response(
        "alpha beta gamma",
        user_id="u1",
        origin="voice",
    )

    assert "context pipeline is temporarily unavailable" in response.display_text.lower()
    orchestrator._handle_research_route.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_research_route_still_allows_three_word_query() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="research")
    orchestrator._handle_research_route = AsyncMock(
        return_value=ResponseFormatter.build_response("Let me look that up for you.")
    )

    response = await orchestrator._handle_chat_response(
        "alpha beta gamma",
        user_id="u1",
        origin="chat",
    )

    assert "look that up" in response.display_text.lower()
    orchestrator._handle_research_route.assert_awaited_once()


@pytest.mark.asyncio
async def test_play_music_routes_to_media_play() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="media_play")
    orchestrator._handoff_manager.consume_signal = MagicMock(return_value="media")
    orchestrator._handoff_manager.delegate = AsyncMock(
        return_value=AgentHandoffResult(
            handoff_id="handoff-media-router",
            trace_id="trace-media-router",
            source_agent="media",
            status="completed",
            user_visible_text="Opening YouTube search for music.",
            voice_text="Opening YouTube search for music.",
            structured_payload={
                "success": True,
                "action": "play",
                "provider": "youtube",
                "message": "Opening YouTube search for music.",
                "track_name": "music",
            },
            next_action="respond",
            error_code=None,
            error_detail=None,
        )
    )

    response = await orchestrator._handle_chat_response("play music", user_id="u1", origin="chat")

    assert "youtube" in response.display_text.lower()
    orchestrator._handoff_manager.delegate.assert_awaited_once()


@pytest.mark.asyncio
async def test_same_session_requests_are_serialized_in_lane_queue() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    active = 0
    max_active = 0
    order: list[str] = []

    async def _fake_core(message: str, user_id: str, tool_context=None, origin: str = "chat"):
        nonlocal active, max_active
        del user_id, tool_context, origin
        active += 1
        max_active = max(max_active, active)
        order.append(f"start:{message}")
        await asyncio.sleep(0.05 if message == "first" else 0.0)
        order.append(f"end:{message}")
        active -= 1
        return ResponseFormatter.build_response(message)

    orchestrator._handle_chat_response_core = _fake_core
    ctx = SimpleNamespace(session_id="s1")

    first_task = asyncio.create_task(
        orchestrator._handle_chat_response("first", user_id="u1", tool_context=ctx, origin="chat")
    )
    await asyncio.sleep(0.01)
    second_task = asyncio.create_task(
        orchestrator._handle_chat_response("second", user_id="u1", tool_context=ctx, origin="chat")
    )

    first_result, second_result = await asyncio.gather(first_task, second_task)

    assert first_result.display_text == "first"
    assert second_result.display_text == "second"
    assert max_active == 1
    assert order == ["start:first", "end:first", "start:second", "end:second"]


@pytest.mark.asyncio
async def test_lane_queue_drops_on_fifth_request_due_to_capacity() -> None:
    # Lane queue: MAX_QUEUE_DEPTH=3 waiting + 1 in-flight = 4 total capacity.
    # The 5th concurrent message is the first one dropped.
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())

    async def _fake_core(message: str, user_id: str, tool_context=None, origin: str = "chat"):
        del user_id, tool_context, origin
        if message == "first":
            await asyncio.sleep(0.08)
        return ResponseFormatter.build_response(message)

    orchestrator._handle_chat_response_core = _fake_core
    ctx = SimpleNamespace(session_id="s-overflow")

    first_task = asyncio.create_task(
        orchestrator._handle_chat_response("first", user_id="u1", tool_context=ctx, origin="chat")
    )
    await asyncio.sleep(0.01)
    queued_tasks = [
        asyncio.create_task(
            orchestrator._handle_chat_response(text, user_id="u1", tool_context=ctx, origin="chat")
        )
        for text in ("second", "third", "fourth", "fifth")
    ]

    results = await asyncio.gather(first_task, *queued_tasks)
    dropped = [
        response
        for response in results
        if "still working on previous requests" in response.display_text.lower()
    ]

    assert len(dropped) == 1
    assert results[1].display_text == "I'm still working on previous requests. Please try again."


@pytest.mark.asyncio
async def test_chat_route_filters_task_completion_history_and_stays_fresh(monkeypatch) -> None:
    class _Stream:
        def __init__(self, text: str):
            self._text = text
            self._done = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._done:
                raise StopAsyncIteration
            self._done = True
            return SimpleNamespace(content=self._text)

        async def aclose(self):
            return None

    seen_tools: list[list[object]] = []

    class _FakeRoleLLM:
        def __init__(self, _smart_llm):
            pass

        async def chat(self, **kwargs):
            seen_tools.append(list(kwargs.get("tools") or []))
            return _Stream("Here's a joke about loops.")

    class _Builder:
        def __init__(self):
            self.history_seen: list[dict] = []

        async def build_for_chat(
            self,
            user_message: str,
            user_id: str | None,
            session_id: str | None,
            conversation_history: list[dict],
            system_prompt: str,
            retriever: object,
            origin: str = "chat",
        ):
            del user_message, user_id, session_id, system_prompt, retriever, origin
            self.history_seen = list(conversation_history)
            return []

        async def build_for_voice(self, *args, **kwargs):
            del args, kwargs
            return []

    orchestrator = AgentOrchestrator(MagicMock(), SimpleNamespace(smart_llm=object()))
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="chat")
    orchestrator._phase6_context_builder_enabled = True
    builder = _Builder()
    orchestrator._context_builder = builder
    orchestrator.enable_chat_tools = True
    orchestrator._resolve_phase3_chat_tools = MagicMock(return_value=[object()])
    orchestrator._build_agent_response = AsyncMock(
        return_value=ResponseFormatter.build_response("Here's a joke about loops.")
    )
    orchestrator._conversation_history = [
        {"role": "assistant", "content": "I completed the action.", "source": "tool_output"},
        {"role": "assistant", "content": "Action cancelled.", "source": "tool_output"},
        {"role": "assistant", "content": "Sure, what do you want next?", "source": "history"},
    ]

    monkeypatch.setattr("core.llm.role_llm.RoleLLM", _FakeRoleLLM)

    response = await orchestrator._handle_chat_response(
        "tell me a joke",
        user_id="u1",
        tool_context=SimpleNamespace(session_id="s-chat"),
        origin="chat",
    )

    serialized_history = " ".join(
        str(item.get("content", "")) for item in builder.history_seen if isinstance(item, dict)
    ).lower()
    assert "completed the action" not in serialized_history
    assert "action cancelled" not in serialized_history
    assert seen_tools and seen_tools[0] == []
    assert "completed" not in response.display_text.lower()
    assert "cancelled" not in response.display_text.lower()


@pytest.mark.asyncio
async def test_user_memory_queries_route_to_chat_not_identity() -> None:
    router = AgentRouter(_MappingLLM({"do you know my name": "identity"}))
    assert await router.route("do you know my name", "u1") == "chat"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "utterance",
    [
        "my name is Harsha",
        "what is my name",
        "remember my favorite language is Rust",
    ],
)
async def test_first_person_memory_phrases_route_to_chat(utterance: str) -> None:
    router = AgentRouter(_MappingLLM({utterance: "identity"}))
    assert await router.route(utterance, "u1") == "chat"


def test_identity_patterns_do_not_include_broad_name_or_my_tokens() -> None:
    pattern_blob = "\n".join(AgentRouter._IDENTITY_PATTERNS)
    assert r"\bname\b" not in pattern_blob
    assert r"\bmy\b" not in pattern_blob


def test_fastpath_group_count_contract() -> None:
    source = textwrap.dedent(inspect.getsource(FastPathRouter.detect_direct_tool_intent))
    tree = ast.parse(source)
    groups: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "DirectToolIntent":
            continue
        if len(node.args) < 4:
            continue
        group_arg = node.args[3]
        if isinstance(group_arg, ast.Constant) and isinstance(group_arg.value, str):
            groups.add(group_arg.value)

    assert groups == {"time", "app", "media", "youtube", "notes"}


def test_extract_name_from_profile_fact_memory_message() -> None:
    messages = [
        {
            "role": "user",
            "source": "memory",
            "content": "[Memory from previous conversations:]\n- User profile fact: name=Harsha",
        }
    ]
    assert AgentOrchestrator._extract_name_from_memory_messages(messages) == "Harsha"


@pytest.mark.asyncio
async def test_small_talk_does_not_trigger_fast_path_intent() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    assert orchestrator._detect_direct_tool_intent("how are you", origin="chat") is None


@pytest.mark.asyncio
async def test_role_status_queries_use_chat_fast_path() -> None:
    router = AgentRouter(
        _MappingLLM(
            {
                "who is the CEO of OpenAI": "chat",
                "who is the current prime minister of Japan": "research",
            }
        )
    )
    assert await router.route("who is the CEO of OpenAI", "u1") == "chat"  # Simple facts now fast-path
    assert await router.route("who is the current prime minister of Japan", "u1") == "research"


@pytest.mark.asyncio
async def test_freshness_override_does_not_clobber_media_play_routing() -> None:
    utterance = "Play the recent movie songs in YouTube"
    router = AgentRouter(_MappingLLM({utterance: "media_play"}))

    assert await router.route(utterance, "u1") == "media_play"


@pytest.mark.asyncio
async def test_freshness_override_still_applies_to_non_media_queries() -> None:
    utterance = "latest news about AI"
    router = AgentRouter(_MappingLLM({utterance: "chat"}))

    assert await router.route(utterance, "u1") == "research"


@pytest.mark.asyncio
async def test_windows_open_query_does_not_use_fast_path() -> None:
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="system")
    orchestrator._execute_tool_call = AsyncMock(side_effect=AssertionError("fast-path should not run"))
    system_agent = MagicMock()
    system_agent.run = AsyncMock(
        return_value=SimpleNamespace(
            action_type=SimpleNamespace(value="inspect"),
            success=True,
            message="System route handled.",
            detail="ok",
            rollback_available=False,
            trace_id="trace-test",
        )
    )
    orchestrator._resolve_system_agent = MagicMock(return_value=system_agent)

    response = await orchestrator._handle_chat_response(
        "what windows are currently open?",
        user_id="u1",
        origin="chat",
    )

    orchestrator._router.route.assert_awaited_once()
    system_agent.run.assert_awaited_once()
    assert "system route handled" in response.display_text.lower()


@pytest.mark.asyncio
async def test_router_shadow_envelope_logs_without_changing_legacy_route(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ROUTER_SHADOW", "true")
    monkeypatch.setenv("LLM_ROUTER_ACTIVE", "false")
    llm = _ShadowLLM()
    router = AgentRouter(llm)

    route = await router.route("hello there", "u1")

    assert route == "chat"
    assert any("routing shadow evaluator" in prompt for prompt in llm.prompts)
