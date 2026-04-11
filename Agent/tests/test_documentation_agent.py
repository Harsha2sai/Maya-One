import pytest

from core.agents.base import AgentContext
from core.agents.contracts import AgentHandoffRequest, HandoffSignal
from core.agents.documentation_agent import DocumentationAgent
from core.agents.handoff_manager import HandoffManager
from core.agents.registry import AgentRegistry


def _context(**custom_data):
    return AgentContext(
        user_id="u1",
        user_role="USER",
        conversation_history=[],
        memory_context="",
        custom_data=custom_data,
    )


def _request(**overrides) -> AgentHandoffRequest:
    payload = {
        "handoff_id": "handoff-docs-1",
        "trace_id": "trace-docs-1",
        "conversation_id": "conversation-docs-1",
        "task_id": "task-docs-1",
        "parent_agent": "maya",
        "active_agent": "maya",
        "target_agent": "documentation",
        "intent": "documentation",
        "user_text": "generate API docs",
        "context_slice": "User requested docs generation.",
        "execution_mode": "planning",
        "delegation_depth": 0,
        "max_depth": 1,
        "handoff_reason": "docs_test",
        "metadata": {"user_id": "u1"},
    }
    payload.update(overrides)
    return AgentHandoffRequest(**payload)


@pytest.mark.asyncio
async def test_documentation_agent_generates_readme(tmp_path):
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Existing\n", encoding="utf-8")

    agent = DocumentationAgent()
    readme = await agent.generate_readme(str(tmp_path))

    assert "# Project README" in readme
    assert "Primary language(s):" in readme
    assert "Python" in readme
    assert "`src`" in readme


@pytest.mark.asyncio
async def test_documentation_agent_updates_changelog():
    agent = DocumentationAgent()
    changelog = await agent.update_changelog(
        [
            "feat(core): add docs generation",
            "fix(parser): avoid crash",
            "docs(readme): clarify setup",
            "test(agent): add coverage",
        ]
    )

    assert "### Added" in changelog
    assert "feat(core): add docs generation" in changelog
    assert "### Fixed" in changelog
    assert "fix(parser): avoid crash" in changelog
    assert "### Docs" in changelog
    assert "### Tests" in changelog


@pytest.mark.asyncio
async def test_documentation_agent_generates_api_docs(tmp_path):
    module_path = tmp_path / "calculator.py"
    module_path.write_text(
        '"""Simple calculator module."""\n\n'
        "class Calculator:\n"
        '    """Math operations."""\n'
        "    def add(self, a, b):\n"
        '        """Add values."""\n'
        "        return a + b\n\n"
        "def sum_two(a, b):\n"
        '    """Sum two values."""\n'
        "    return a + b\n",
        encoding="utf-8",
    )

    agent = DocumentationAgent()
    api_docs = await agent.generate_api_docs(str(module_path))

    assert "API Docs: calculator.py" in api_docs
    assert "Simple calculator module." in api_docs
    assert "`Calculator`" in api_docs
    assert "`sum_two(a, b)`" in api_docs


@pytest.mark.asyncio
async def test_documentation_agent_execute_with_context_metadata(tmp_path):
    module_path = tmp_path / "module.py"
    module_path.write_text("def ping(x):\n    return x\n", encoding="utf-8")

    agent = DocumentationAgent()
    response = await agent.execute("generate api docs", _context(module_path=str(module_path)))

    assert response.display_text == "API docs generated."
    assert response.structured_data["document_type"] == "api_docs"
    assert "ping(x)" in response.structured_data["content"]


@pytest.mark.asyncio
async def test_documentation_agent_is_registered_and_signal_maps():
    registry = AgentRegistry()
    assert registry.get_agent("documentation") is not None

    manager = HandoffManager(registry)
    signal = HandoffSignal(
        signal_name="transfer_to_documentation",
        reason="docs update requested",
        execution_mode="planning",
        context_hint="generate docs",
    )

    assert manager.consume_signal(signal) == "documentation"

    result = await manager.delegate(
        _request(
            metadata={
                "user_id": "u1",
                "codebase_path": ".",
                "commits": ["feat(docs): baseline"],
            }
        )
    )
    assert result.status == "completed"
    assert result.source_agent == "documentation"
    assert result.structured_payload["codebase_path"] == "."
    assert result.structured_payload["has_commits"] is True
