"""
AgentScope model config wiring tests.

Validates:
- ReActAgent construction succeeds for all supported providers
- Primary path is used when API key is present (not fallback)
- Fallback triggers cleanly when API key is missing
- Provider map covers all Maya-supported LLM providers
- _build_model raises ReActAgentBuildError for unsupported provider
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.agents.subagent.manager import SubAgentManager, ReActAgentBuildError
from core.agents.subagent.types import SubAgentStatus
from core.messaging import MayaMsgHub


# ── Construction ──────────────────────────────────────────────────────────────

def test_build_model_groq_succeeds():
    """ReActAgent model builds with GROQ_API_KEY set."""
    manager = SubAgentManager(msg_hub=MayaMsgHub())
    with patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": "test-key", "LLM_MODEL": "llama-3.3-70b-versatile"}):
        model = manager._build_model()
        assert model is not None
        assert model.model_name == "llama-3.3-70b-versatile"


def test_build_model_openai_succeeds():
    """ReActAgent model builds with OPENAI_API_KEY set."""
    manager = SubAgentManager(msg_hub=MayaMsgHub())
    with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key", "LLM_MODEL": "gpt-4o-mini"}):
        model = manager._build_model()
        assert model is not None
        assert model.model_name == "gpt-4o-mini"


def test_build_model_missing_key_raises():
    """ReActAgentBuildError raised when API key env var is missing."""
    manager = SubAgentManager(msg_hub=MayaMsgHub())
    env = {"LLM_PROVIDER": "groq", "LLM_MODEL": "llama-3.3-70b-versatile"}
    # Ensure GROQ_API_KEY is absent
    with patch.dict(os.environ, env):
        os.environ.pop("GROQ_API_KEY", None)
        with pytest.raises(ReActAgentBuildError, match="GROQ_API_KEY"):
            manager._build_model()


def test_build_model_unsupported_provider_raises():
    """ReActAgentBuildError raised for unknown provider."""
    manager = SubAgentManager(msg_hub=MayaMsgHub())
    with patch.dict(os.environ, {"LLM_PROVIDER": "unknown_provider", "LLM_MODEL": "x"}):
        with pytest.raises(ReActAgentBuildError, match="Unsupported"):
            manager._build_model()


def test_build_react_agent_constructs_for_all_types():
    """ReActAgent constructs for every agent type without error."""
    manager = SubAgentManager(msg_hub=MayaMsgHub())
    agent_types = ["coder", "reviewer", "researcher", "architect", "tester", "security", "documentation"]

    with patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": "test-key", "LLM_MODEL": "llama-3.3-70b-versatile"}):
        for agent_type in agent_types:
            agent = manager._build_react_agent(agent_type, context=None)
            assert agent is not None, f"Failed to build agent for type: {agent_type}"
            assert agent.name == agent_type


# ── Primary path vs fallback ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_primary_path_used_when_key_present():
    """When API key is set, primary ReActAgent path is used, not fallback."""
    manager = SubAgentManager(msg_hub=MayaMsgHub())

    mock_response = MagicMock()
    mock_response.content = "def hello(): return 'world'"

    mock_agent = MagicMock()
    mock_agent.reply = AsyncMock(return_value=mock_response)

    with patch.dict(os.environ, {
        "LLM_PROVIDER": "groq",
        "GROQ_API_KEY": "test-key",
        "LLM_MODEL": "llama-3.3-70b-versatile",
    }):
        # Patch _build_react_agent to return our mock
        with patch.object(manager, "_build_react_agent", return_value=mock_agent):
            # Clear PYTEST_CURRENT_TEST so primary path runs
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("PYTEST_CURRENT_TEST", None)

                from core.agents.subagent.types import SubAgentInstance, SubAgentStatus
                instance = SubAgentInstance(
                    id="test-001",
                    agent_type="coder",
                    task="write a hello function",
                    status=SubAgentStatus.PENDING,
                )

                result = await manager._execute(instance, context=None)

    assert result == "def hello(): return 'world'"
    mock_agent.reply.assert_called_once()


@pytest.mark.asyncio
async def test_fallback_used_when_key_missing():
    """When API key is missing, fallback path returns stub response."""
    manager = SubAgentManager(msg_hub=MayaMsgHub())

    with patch.dict(os.environ, {"LLM_PROVIDER": "groq", "LLM_MODEL": "llama-3.3-70b-versatile"}):
        os.environ.pop("GROQ_API_KEY", None)
        os.environ.pop("PYTEST_CURRENT_TEST", None)

        from core.agents.subagent.types import SubAgentInstance, SubAgentStatus
        instance = SubAgentInstance(
            id="test-002",
            agent_type="researcher",
            task="research quantum computing",
            status=SubAgentStatus.PENDING,
        )

        result = await manager._execute(instance, context=None)

    assert "Fallback path" in result
    assert "researcher" in result


@pytest.mark.asyncio
async def test_fallback_used_in_pytest_environment():
    """PYTEST_CURRENT_TEST guard keeps tests deterministic."""
    manager = SubAgentManager(msg_hub=MayaMsgHub())

    with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "test_something"}):
        from core.agents.subagent.types import SubAgentInstance, SubAgentStatus
        instance = SubAgentInstance(
            id="test-003",
            agent_type="coder",
            task="write tests",
            status=SubAgentStatus.PENDING,
        )
        result = await manager._execute(instance, context=None)

    assert "Fallback path" in result


# ── Provider map completeness ─────────────────────────────────────────────────

def test_all_maya_providers_are_mapped():
    """Every provider in Maya's settings is covered by the provider map."""
    manager = SubAgentManager(msg_hub=MayaMsgHub())
    maya_providers = {"groq", "openai", "anthropic", "gemini", "deepseek"}

    for provider in maya_providers:
        key_env_var = {
            "groq": "GROQ_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
        }[provider]

        with patch.dict(os.environ, {"LLM_PROVIDER": provider, key_env_var: "test-key", "LLM_MODEL": "test-model"}):
            # Should not raise — just construct the model object
            model = manager._build_model()
            assert model is not None, f"Provider '{provider}' failed to build model"
