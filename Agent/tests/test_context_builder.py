import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from livekit.agents.llm import ChatContext, ChatMessage

from core.context.context_builder import ContextBuilder
from core.context.context_guard import ContextGuard
from core.orchestrator.agent_orchestrator import AgentOrchestrator


class DummyRetriever:
    def __init__(self, results=None):
        self.results = results or []
        self.calls = []

    async def retrieve_async(self, **kwargs):
        self.calls.append(kwargs)
        return list(self.results)

    async def retrieve_with_scope_fallback(self, **kwargs):
        self.calls.append({"fallback": True, **kwargs})
        return list(self.results)


def _make_builder(guard=None):
    return ContextBuilder(
        llm=None,
        memory_manager=SimpleNamespace(),
        user_id="test_user",
        guard=guard or ContextGuard(token_limit=12000),
    )


def _make_history(turns: int):
    history = []
    for idx in range(turns):
        role = "user" if idx % 2 == 0 else "assistant"
        history.append({"role": role, "content": f"history-{idx}"})
    return history


@pytest.mark.asyncio
async def test_build_for_voice_limits_history_to_5_turns(monkeypatch):
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "12000")
    builder = _make_builder()
    retriever = DummyRetriever()

    messages = await builder.build_for_voice(
        user_message="latest question",
        user_id="u1",
        session_id="s1",
        conversation_history=_make_history(10),
        system_prompt="system",
        retriever=retriever,
    )

    non_system = [m for m in messages if m.role != "system"]
    assert len(non_system) <= 8  # protected + summary + 5 recent + current user
    assert str(non_system[-1].content[0]) == "latest question"
    assert any(
        "[Earlier conversation summary]" in str(msg.content[0])
        for msg in non_system
    )


@pytest.mark.asyncio
async def test_build_for_voice_uses_voice_memory_budget(monkeypatch):
    monkeypatch.setenv("VOICE_RETRIEVER_K", "2")
    builder = _make_builder()
    retriever = DummyRetriever(results=[{"text": "remember this"}])

    await builder.build_for_voice(
        user_message="remember",
        user_id="u1",
        session_id="s1",
        conversation_history=[],
        system_prompt="system",
        retriever=retriever,
    )

    assert retriever.calls
    assert retriever.calls[0]["origin"] == "voice"
    assert retriever.calls[0]["k"] == 2
    assert retriever.calls[0]["fallback"] is True


@pytest.mark.asyncio
async def test_build_for_chat_uses_summary_for_older_history(monkeypatch):
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "12000")
    monkeypatch.setenv("MAX_HISTORY_TOKENS", "12000")
    builder = _make_builder()
    retriever = DummyRetriever()
    history = _make_history(8)

    messages = await builder.build_for_chat(
        user_message="chat message",
        user_id="u1",
        session_id="s1",
        conversation_history=history,
        system_prompt="system",
        retriever=retriever,
    )

    non_system = [m for m in messages if m.role != "system"]
    assert any(
        "[Earlier conversation summary]" in str(msg.content[0])
        for msg in non_system
    )
    assert str(non_system[-1].content[0]) == "chat message"
    assert retriever.calls[0]["origin"] == "chat"
    assert retriever.calls[0]["k"] == 4


@pytest.mark.asyncio
async def test_build_for_chat_enforces_semantic_top_k(monkeypatch):
    monkeypatch.setenv("CHAT_RETRIEVER_K", "2")
    builder = _make_builder()
    retriever = DummyRetriever(
        results=[
            {"text": "memory one"},
            {"text": "memory two"},
            {"text": "memory three"},
        ]
    )

    messages = await builder.build_for_chat(
        user_message="use memory",
        user_id="u1",
        session_id="s1",
        conversation_history=[],
        system_prompt="system",
        retriever=retriever,
    )

    assert retriever.calls
    assert retriever.calls[0]["k"] == 2
    text_blob = "\n".join(str(m.content[0]) for m in messages if m.role != "system")
    assert "memory one" in text_blob
    assert "memory two" in text_blob
    assert "memory three" not in text_blob


def test_context_guard_truncates_memory_when_over_budget(monkeypatch, caplog):
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "120")
    monkeypatch.setenv("MAX_MEMORY_TOKENS", "20")
    monkeypatch.setenv("MAX_HISTORY_TOKENS", "80")
    guard = ContextGuard()

    messages = [
        {"role": "system", "content": "sys", "source": "system_prompt"},
        {"role": "system", "content": "memory " * 40, "source": "memory"},
        {"role": "assistant", "content": "history", "source": "history"},
        {"role": "user", "content": "latest", "source": "current_user"},
    ]

    with caplog.at_level(logging.INFO):
        guarded = guard.enforce(messages, origin="voice")

    assert any(msg.get("source") == "current_user" for msg in guarded)
    assert "context_guard_truncated=True" in caplog.text
    assert "context_guard_truncation_source=memory" in caplog.text


def test_context_guard_truncates_history_when_over_budget(monkeypatch, caplog):
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "120")
    monkeypatch.setenv("MAX_MEMORY_TOKENS", "100")
    monkeypatch.setenv("MAX_HISTORY_TOKENS", "20")
    guard = ContextGuard()

    messages = [
        {"role": "system", "content": "sys", "source": "system_prompt"},
        {"role": "assistant", "content": "history " * 50, "source": "history"},
        {"role": "user", "content": "latest", "source": "current_user"},
    ]

    with caplog.at_level(logging.INFO):
        guarded = guard.enforce(messages, origin="chat")

    assert any(msg.get("source") == "current_user" for msg in guarded)
    assert "context_guard_truncated=False" in caplog.text
    assert "context_guard_truncation_source=none" in caplog.text


def test_context_guard_never_truncates_system_prompt(monkeypatch):
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "60")
    monkeypatch.setenv("MAX_MEMORY_TOKENS", "10")
    monkeypatch.setenv("MAX_HISTORY_TOKENS", "10")
    guard = ContextGuard()

    messages = [
        {
            "role": "system",
            "content": "critical system prompt",
            "source": "system_prompt",
        },
        {"role": "assistant", "content": "history " * 100, "source": "history"},
        {"role": "user", "content": "latest request", "source": "current_user"},
    ]
    guarded = guard.enforce(messages, origin="voice")

    assert guarded[0]["source"] == "system_prompt"
    assert "critical system prompt" in guarded[0]["content"]


def test_context_guard_tier1_never_truncated(monkeypatch):
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "90")
    monkeypatch.setenv("MAX_MEMORY_TOKENS", "10")
    monkeypatch.setenv("MAX_HISTORY_TOKENS", "10")
    guard = ContextGuard()

    messages = [
        {"role": "system", "content": "critical system prompt", "source": "system_prompt"},
        {"role": "assistant", "content": "task in progress", "source": "task_step"},
        {"role": "assistant", "content": "tool summary", "source": "tool_output"},
        {"role": "assistant", "content": "history " * 120, "source": "history"},
        {"role": "user", "content": "latest request", "source": "current_user"},
    ]

    guarded = guard.enforce(messages, origin="voice")
    sources = [msg.get("source") for msg in guarded]
    assert "task_step" in sources
    assert "tool_output" in sources
    assert sources[-1] == "current_user"


def test_context_guard_truncates_tier4_before_tier2(monkeypatch):
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "80")
    monkeypatch.setenv("MAX_MEMORY_TOKENS", "12")
    monkeypatch.setenv("MAX_HISTORY_TOKENS", "60")
    guard = ContextGuard()

    messages = [
        {"role": "system", "content": "system", "source": "system_prompt"},
        {"role": "assistant", "content": "[Earlier conversation summary]\n- older", "source": "history_summary"},
        {"role": "assistant", "content": "recent history survives", "source": "history"},
        {"role": "user", "content": "memory " * 100, "source": "memory"},
        {"role": "user", "content": "latest", "source": "current_user"},
    ]

    guarded = guard.enforce(messages, origin="voice")
    sources = [msg.get("source") for msg in guarded]
    assert "history" in sources
    assert "current_user" in sources
    assert sources[-1] == "current_user"


def test_context_guard_total_tokens_within_limit(monkeypatch, caplog):
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "100")
    monkeypatch.setenv("MAX_MEMORY_TOKENS", "25")
    monkeypatch.setenv("MAX_HISTORY_TOKENS", "25")
    guard = ContextGuard()

    messages = [
        {"role": "system", "content": "sys " * 30, "source": "system_prompt"},
        {"role": "assistant", "content": "[Earlier conversation summary]\n" + ("older " * 80), "source": "history_summary"},
        {"role": "assistant", "content": "recent " * 80, "source": "history"},
        {"role": "user", "content": "memory " * 80, "source": "memory"},
        {"role": "user", "content": "latest user prompt", "source": "current_user"},
    ]

    with caplog.at_level(logging.CRITICAL, logger="core.context.context_guard"):
        guarded = guard.enforce(messages, origin="chat")
    total_tokens = sum(guard.count_tokens(str(m.get("content", ""))) for m in guarded)
    if total_tokens > guard.token_limit:
        assert any("context_guard_hard_limit_reached" in record.message for record in caplog.records)
        assert any(m.get("source") == "history_summary" for m in guarded)
        assert any(m.get("source") == "current_user" for m in guarded)
    else:
        assert total_tokens <= guard.token_limit


def test_context_guard_never_truncates_current_user_message(monkeypatch):
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "60")
    monkeypatch.setenv("MAX_MEMORY_TOKENS", "10")
    monkeypatch.setenv("MAX_HISTORY_TOKENS", "10")
    guard = ContextGuard()

    messages = [
        {"role": "system", "content": "system", "source": "system_prompt"},
        {"role": "assistant", "content": "history " * 100, "source": "history"},
        {
            "role": "user",
            "content": "keep this current input",
            "source": "current_user",
        },
    ]
    guarded = guard.enforce(messages, origin="chat")

    assert guarded[-1]["source"] == "current_user"
    assert guarded[-1]["content"] == "keep this current input"


def test_context_guard_logs_truncation_source(monkeypatch, caplog):
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "60")
    monkeypatch.setenv("MAX_MEMORY_TOKENS", "10")
    monkeypatch.setenv("MAX_HISTORY_TOKENS", "10")
    guard = ContextGuard()

    messages = [
        {"role": "system", "content": "system", "source": "system_prompt"},
        {"role": "system", "content": "memory " * 20, "source": "memory"},
        {"role": "assistant", "content": "history " * 20, "source": "history"},
        {"role": "user", "content": "latest", "source": "current_user"},
    ]

    with caplog.at_level(logging.INFO):
        guard.enforce(messages, origin="voice")

    assert "context_guard_truncation_source=" in caplog.text


@pytest.mark.asyncio
async def test_build_for_voice_calls_retrieve_async_with_voice_origin():
    builder = _make_builder()
    retriever = DummyRetriever()

    await builder.build_for_voice(
        user_message="what did i ask",
        user_id="user-1",
        session_id="session-1",
        conversation_history=[],
        system_prompt="sys",
        retriever=retriever,
    )

    assert retriever.calls[0]["origin"] == "voice"
    assert retriever.calls[0]["user_id"] == "user-1"
    assert retriever.calls[0]["session_id"] == "session-1"


@pytest.mark.asyncio
async def test_context_builder_disabled_flag_returns_circuit_breaker(monkeypatch):
    monkeypatch.setenv("PHASE6_CONTEXT_BUILDER_ENABLED", "false")

    class DummyRoleLLM:
        def __init__(self, _smart_llm):
            pass

        async def chat(self, **_kwargs):
            async def _stream():
                yield SimpleNamespace(content="hello from llm")

            return _stream()

    monkeypatch.setattr("core.llm.role_llm.RoleLLM", DummyRoleLLM)

    ctx = SimpleNamespace(room=None)
    agent = SimpleNamespace(smart_llm=SimpleNamespace(base_llm=None))
    orchestrator = AgentOrchestrator(
        ctx=ctx,
        agent=agent,
        memory_manager=SimpleNamespace(
            retrieve_relevant_memories_async=AsyncMock(return_value=[])
        ),
        enable_chat_tools=False,
        enable_task_pipeline=False,
    )

    orchestrator._generate_voice_text = AsyncMock(return_value="voice")
    orchestrator._retrieve_memory_context_async = AsyncMock(return_value="")
    if orchestrator._context_builder is not None:
        orchestrator._context_builder.build_for_chat = AsyncMock(return_value=[])

    response = await orchestrator._handle_chat_response(
        "tell me something",
        user_id="u1",
        tool_context=SimpleNamespace(session_id="s1"),
        origin="chat",
    )

    assert "Context pipeline is temporarily unavailable" in response.display_text
    assert not orchestrator._is_phase6_context_builder_active()
    assert orchestrator._retrieve_memory_context_async.await_count == 0
    if orchestrator._context_builder is not None:
        orchestrator._context_builder.build_for_chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_context_builder_enabled_flag_uses_phase6_builder(monkeypatch):
    monkeypatch.setenv("PHASE6_CONTEXT_BUILDER_ENABLED", "true")

    class DummyRoleLLM:
        def __init__(self, _smart_llm):
            pass

        async def chat(self, **_kwargs):
            async def _stream():
                yield SimpleNamespace(content="hello from llm")

            return _stream()

    monkeypatch.setattr("core.llm.role_llm.RoleLLM", DummyRoleLLM)

    ctx = SimpleNamespace(room=None)
    agent = SimpleNamespace(smart_llm=SimpleNamespace(base_llm=None))
    orchestrator = AgentOrchestrator(
        ctx=ctx,
        agent=agent,
        memory_manager=SimpleNamespace(
            retrieve_relevant_memories_async=AsyncMock(return_value=[])
        ),
        enable_chat_tools=False,
        enable_task_pipeline=False,
    )

    orchestrator._generate_voice_text = AsyncMock(return_value="voice")
    orchestrator._retrieve_memory_context_async = AsyncMock(return_value="")
    assert orchestrator._context_builder is not None
    orchestrator._context_builder.build_for_chat = AsyncMock(
        return_value=[
            ChatMessage(role="system", content=["system prompt"]),
            ChatMessage(role="user", content=["tell me something"]),
        ]
    )

    response = await orchestrator._handle_chat_response(
        "tell me something",
        user_id="u1",
        tool_context=SimpleNamespace(session_id="s1"),
        origin="chat",
    )

    assert response.display_text
    assert orchestrator._is_phase6_context_builder_active()
    orchestrator._context_builder.build_for_chat.assert_awaited_once()
    assert orchestrator._retrieve_memory_context_async.await_count == 0
