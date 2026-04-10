from types import SimpleNamespace
from unittest.mock import MagicMock

from core.orchestrator.agent_orchestrator import AgentOrchestrator


def test_transcript_platform_search_uses_active_research_subject() -> None:
    orchestrator = AgentOrchestrator(SimpleNamespace(room=None), MagicMock())
    orchestrator._store_research_context(
        query="what is the war between iran and america",
        summary="The Iran and America war situation is evolving.",
    )

    intent = orchestrator._detect_direct_tool_intent("open the youtube and search about it", origin="voice")

    assert intent is not None
    assert intent.tool == "open_app"
    assert intent.group == "youtube"
    assert "youtube search for" in intent.args.get("app_name", "")
    assert "youtube search for youtube" not in intent.args.get("app_name", "").lower()
    assert "iran and america war" in intent.args.get("app_name", "").lower()
