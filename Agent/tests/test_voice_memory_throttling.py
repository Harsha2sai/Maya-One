import time
from unittest.mock import MagicMock

import pytest

from core.orchestrator.agent_orchestrator import AgentOrchestrator


@pytest.fixture
def orchestrator():
    agent = MagicMock()
    agent.smart_llm = None
    orch = AgentOrchestrator(MagicMock(), agent)
    return orch


def test_memory_skipped_for_fast_path_voice(orchestrator):
    skip, reason = orchestrator._should_skip_memory(
        "change song",
        origin="voice",
        routing_mode_type="fast_path",
    )
    assert skip is True
    assert reason == "fast_path"


def test_memory_skipped_for_direct_action_voice(orchestrator):
    skip, reason = orchestrator._should_skip_memory(
        "set a reminder for 5pm",
        origin="voice",
        routing_mode_type="direct_action",
    )
    assert skip is True
    assert reason == "direct_action"


def test_memory_skipped_for_informational_no_recall_trigger(orchestrator):
    skip, reason = orchestrator._should_skip_memory(
        "what is the weather in hyderabad",
        origin="voice",
        routing_mode_type="informational",
    )
    assert skip is True
    assert reason == "no_recall_trigger"


def test_memory_allowed_for_conversational_recall_trigger(orchestrator):
    skip, reason = orchestrator._should_skip_memory(
        "what did I ask you yesterday",
        origin="voice",
        routing_mode_type="conversational",
    )
    assert skip is False
    assert reason == "conversational"


def test_memory_allowed_for_remember_trigger(orchestrator):
    skip, reason = orchestrator._should_skip_memory(
        "do you remember my name",
        origin="voice",
        routing_mode_type="informational",
    )
    assert skip is False
    assert reason == "conversational"


@pytest.mark.asyncio
async def test_memory_budget_timeout_returns_empty_not_error(orchestrator, monkeypatch):
    def slow_retrieve(_query: str, _k: int = 2):
        time.sleep(0.2)
        return [{"text": "slow result"}]

    monkeypatch.setenv("VOICE_MEMORY_TIMEOUT_S", "0.01")
    orchestrator._retrieve_memories = slow_retrieve
    result = await orchestrator._retrieve_memory_context_async(
        "what did i ask earlier",
        origin="voice",
        routing_mode_type="conversational",
    )
    assert result == ""


@pytest.mark.asyncio
async def test_memory_not_skipped_for_chat_origin(orchestrator, monkeypatch):
    monkeypatch.setenv("MAYA_DISABLE_MEMORY_RETRIEVAL", "false")
    orchestrator._retrieve_memories = lambda _query, _k=5: [{"text": "alpha"}]
    result = await orchestrator._retrieve_memory_context_async(
        "random context value",
        origin="chat",
        routing_mode_type="informational",
    )
    assert "Relevant past memories" in result


@pytest.mark.asyncio
async def test_memory_skip_reason_logged_correctly(orchestrator, caplog):
    with caplog.at_level("INFO"):
        result = await orchestrator._retrieve_memory_context_async(
            "what's the weather in hyderabad",
            origin="voice",
            routing_mode_type="informational",
        )
    assert result == ""
    assert "memory_skipped=true" in caplog.text
    assert "memory_skip_reason=no_recall_trigger" in caplog.text
