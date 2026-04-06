from unittest.mock import AsyncMock, MagicMock

import pytest

from core.orchestrator.agent_orchestrator import AgentOrchestrator


@pytest.fixture
def orchestrator():
    agent = MagicMock()
    agent.smart_llm = None
    return AgentOrchestrator(MagicMock(), agent)


@pytest.mark.asyncio
async def test_build_agent_response_sanitizes_markup_and_uses_voice_fallback(orchestrator):
    orchestrator._generate_voice_text = AsyncMock(return_value="clean voice")

    response = await orchestrator._build_agent_response(
        role_llm=MagicMock(),
        raw_output='{"display_text":"Done <function>open_app{}</function>","voice_text":"Done"}',
    )

    assert response.display_text == "Done"
    assert response.voice_text == "clean voice"
    orchestrator._generate_voice_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_agent_response_uses_voice_fallback_when_voice_missing(orchestrator):
    orchestrator._generate_voice_text = AsyncMock(return_value="short spoken summary")

    response = await orchestrator._build_agent_response(
        role_llm=MagicMock(),
        raw_output='{"display_text":"Here is the answer.","voice_text":""}',
    )

    assert response.display_text == "Here is the answer."
    assert response.voice_text == "short spoken summary"
    orchestrator._generate_voice_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_voice_text_timeout_records_metrics(orchestrator):
    orchestrator._run_theless_synthesis_with_timeout = AsyncMock(return_value=("", "timeout"))

    result = await orchestrator._generate_voice_text(MagicMock(), "Long display text")

    assert result == ""
    assert orchestrator._synthesis_total == 1
    assert orchestrator._synthesis_timeout_total == 1
    assert orchestrator._synthesis_fallback_total == 1


@pytest.mark.asyncio
async def test_run_theless_synthesis_with_timeout_returns_error_on_exception(orchestrator):
    orchestrator._run_theless_synthesis = AsyncMock(side_effect=RuntimeError("boom"))

    text, status = await orchestrator._run_theless_synthesis_with_timeout(chat_ctx=MagicMock())

    assert text == ""
    assert status == "error"
