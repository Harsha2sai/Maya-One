from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.intent.classifier import IntentResult, IntentType
from core.routing.router import ExecutionRouter


class _NoopMonitor:
    def record_metric(self, *args, **kwargs):
        del args, kwargs
        return None


@pytest.mark.asyncio
async def test_execution_router_uses_contextual_classification_when_summary_present(monkeypatch):
    router = ExecutionRouter()
    calls = {"classify": 0, "contextual": 0}
    intent_result = IntentResult(intent_type=IntentType.CONVERSATION, confidence=0.9, reason="test")

    class _Classifier:
        def classify(self, user_text, memory_context=""):
            del user_text, memory_context
            calls["classify"] += 1
            return intent_result

        def classify_with_context(self, user_text, conversation_summary="", memory_context=""):
            del user_text, conversation_summary, memory_context
            calls["contextual"] += 1
            return intent_result

    router.classifier = _Classifier()

    async def _get_context(_query):
        return "Source line one.\nSource line two."

    monkeypatch.setattr(
        "core.intelligence.rag_engine.get_rag_engine",
        lambda: SimpleNamespace(get_context=_get_context),
    )
    monkeypatch.setattr(
        "telemetry.session_monitor.get_session_monitor",
        lambda: _NoopMonitor(),
    )
    router._synthesize_knowledge_response = AsyncMock(return_value="Synthesized answer")

    result = await router.route(
        "what's the reason",
        context={"conversation_summary": "We were discussing market research findings."},
    )

    assert result.handled is True
    assert result.response == "Synthesized answer"
    assert router._synthesize_knowledge_response.await_count == 1
    assert calls["contextual"] == 1
    assert calls["classify"] == 0


@pytest.mark.asyncio
async def test_execution_router_falls_back_to_plain_classify_without_summary(monkeypatch):
    router = ExecutionRouter()
    calls = {"classify": 0, "contextual": 0}
    result_payload = IntentResult(intent_type=IntentType.CONVERSATION, confidence=0.9, reason="x")

    class _Classifier:
        def classify(self, user_text, memory_context=""):
            del user_text, memory_context
            calls["classify"] += 1
            return result_payload

        def classify_with_context(self, user_text, conversation_summary="", memory_context=""):
            del user_text, conversation_summary, memory_context
            calls["contextual"] += 1
            return result_payload

    router.classifier = _Classifier()

    async def _empty_context(_query):
        return ""

    monkeypatch.setattr(
        "core.intelligence.rag_engine.get_rag_engine",
        lambda: SimpleNamespace(get_context=_empty_context),
    )
    monkeypatch.setattr(
        "telemetry.session_monitor.get_session_monitor",
        lambda: _NoopMonitor(),
    )

    result = await router.route("hello there", context={})

    assert result.handled is False
    assert result.needs_llm is True
    assert calls["classify"] == 1
    assert calls["contextual"] == 0


@pytest.mark.asyncio
async def test_synthesize_knowledge_response_returns_fallback_on_empty_snippets():
    router = ExecutionRouter()
    response = await router._synthesize_knowledge_response(
        query="what happened",
        knowledge_context="",
        assistant=None,
        fallback_intro="Here is some information I found:",
    )
    assert response == "Here is some information I found:"
