from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import agent
from core.orchestrator.agent_orchestrator import AgentOrchestrator


class _FakeConversationStore:
    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    async def get_previous_session_turns(self, user_id, current_session_id, turn_limit):
        self.calls.append(
            {
                "user_id": user_id,
                "current_session_id": current_session_id,
                "turn_limit": turn_limit,
            }
        )
        return list(self.turns)


class _FakeStream:
    def __init__(self, text: str):
        self._text = text
        self._emitted = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._emitted:
            raise StopAsyncIteration
        self._emitted = True
        return SimpleNamespace(content=self._text)

    async def aclose(self):
        return None


class _CapturingRoleLLM:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.prompt = ""

    async def chat(self, *, role, chat_ctx, tools):
        messages = chat_ctx.messages() if callable(chat_ctx.messages) else chat_ctx.messages
        if messages:
            content = getattr(messages[-1], "content", "")
            if isinstance(content, list):
                self.prompt = " ".join(str(part) for part in content)
            else:
                self.prompt = str(content)
        return _FakeStream(self.output_text)


@pytest.mark.asyncio
async def test_no_summary_on_first_session():
    store = _FakeConversationStore(turns=[])
    role_llm = SimpleNamespace(chat=AsyncMock())

    summary = await agent.get_previous_session_summary(
        user_id="livekit:user-1",
        current_session_id="session-current",
        max_sentences=3,
        conversation_store=store,
        role_llm=role_llm,
    )

    assert summary is None
    role_llm.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_summary_uses_previous_session_not_current():
    store = _FakeConversationStore(
        turns=[
            {
                "session_id": "session-current",
                "role": "user",
                "content": "this turn belongs to the current session",
            },
            {
                "session_id": "session-prev",
                "role": "user",
                "content": "set a reminder for 9pm",
            },
            {
                "session_id": "session-prev",
                "role": "assistant",
                "content": "Reminder set for 9pm.",
            },
        ]
    )
    role_llm = _CapturingRoleLLM(
        output_text="You asked for a reminder and I set it. We confirmed the 9pm time."
    )

    summary = await agent.get_previous_session_summary(
        user_id="livekit:user-1",
        current_session_id="session-current",
        max_sentences=3,
        conversation_store=store,
        role_llm=role_llm,
    )

    assert summary is not None
    assert "reminder" in summary.lower()
    assert store.calls
    assert store.calls[0]["current_session_id"] == "session-current"
    assert "set a reminder for 9pm" in role_llm.prompt.lower()
    assert "belongs to the current session" not in role_llm.prompt.lower()


@pytest.mark.asyncio
async def test_summary_injected_once_not_per_turn():
    orchestrator = AgentOrchestrator(
        ctx=SimpleNamespace(room=None),
        agent=SimpleNamespace(smart_llm=SimpleNamespace(base_llm=None)),
        memory_manager=SimpleNamespace(),
        ingestor=SimpleNamespace(),
        enable_chat_tools=False,
        enable_task_pipeline=False,
    )

    first = orchestrator.inject_session_continuity_summary(
        "You asked me to set a reminder and I confirmed it."
    )
    second = orchestrator.inject_session_continuity_summary(
        "A second summary should never be injected in the same session."
    )

    continuity_entries = [
        item
        for item in orchestrator._conversation_history
        if item.get("source") == "session_continuity"
    ]

    assert first is True
    assert second is False
    assert len(continuity_entries) == 1
