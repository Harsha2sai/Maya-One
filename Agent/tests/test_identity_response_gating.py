from types import SimpleNamespace
from unittest.mock import MagicMock

from core.orchestrator.agent_orchestrator import AgentOrchestrator


def _make_orchestrator() -> AgentOrchestrator:
    return AgentOrchestrator(SimpleNamespace(room=None), MagicMock())


def test_identity_dominance_detects_identity_queries() -> None:
    orchestrator = _make_orchestrator()
    assert orchestrator._is_identity_dominant_query("Who created you?")
    assert orchestrator._is_identity_dominant_query("What is your name?")


def test_identity_dominance_ignores_regular_factual_query() -> None:
    orchestrator = _make_orchestrator()
    assert not orchestrator._is_identity_dominant_query("What is two plus two?")


def test_strip_identity_preamble_for_non_identity_turn() -> None:
    orchestrator = _make_orchestrator()
    raw = "I'm Maya, and I was created by Harsha. The answer is 4."
    cleaned = orchestrator._strip_identity_preamble_if_needed("what is two plus two", raw)
    assert cleaned == "The answer is 4."


def test_keep_identity_text_for_identity_turn() -> None:
    orchestrator = _make_orchestrator()
    raw = "I'm Maya, and I was created by Harsha."
    cleaned = orchestrator._strip_identity_preamble_if_needed("who created you", raw)
    assert cleaned == raw
