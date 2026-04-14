"""Routing golden dataset and bootstrap contamination regression tests."""

import re
from unittest.mock import MagicMock

import pytest

from core.orchestrator.agent_orchestrator import AgentOrchestrator
from core.orchestrator.agent_router import AgentRouter


ROUTING_GOLDEN = [
    ("what is the time", "get_time", None),
    ("what time is it", "get_time", None),
    ("can you tell me the time", "get_time", None),
    ("current time", "get_time", None),
    # Simple factual queries now fast-path to chat (no research subagent delay)
    ("who is the prime minister of india", "chat", "get_time"),
    ("who is the pm of india", "chat", "get_time"),
    ("who is the ceo of openai", "chat", "get_time"),
    ("what is quantum computing", "chat", "get_time"),
    ("latest news about AI", "research", "media_play"),  # "latest" triggers research
    ("who founded microsoft", "chat", "get_time"),
    ("what is the current GDP of India", "research", None),  # "current" triggers research
    ("who runs google", "chat", None),
    ("play some music", "media_play", "research"),
    ("play the recent movie songs in youtube", "media_play", "research"),
    ("next track", "media_play", "identity"),
    ("pause", "media_play", None),
    ("play songs by AR Rahman", "media_play", "research"),
    ("what is your name", "identity", None),
    ("who are you", "identity", None),
    ("hi", "chat", None),
]

BOOTSTRAP_CONTAMINATION_CASES = [
    "who is the prime minister of india",
    "who is the ceo of openai",
    "what is quantum computing",
    "who founded microsoft",
]

BOOTSTRAP_WITH_TIME = (
    "Conversation resume context:\n"
    "Conversation ID: abc123\n"
    "Recent tool results: The time is 08:27 PM\n\n"
    "Current user message:\n{query}"
)


class _GoldenRouterLLM:
    async def chat(self, prompt: str, **kwargs) -> str:
        del kwargs
        fact_match = re.search(r"Question:\s*(.+?)(?:\nAnswer:|\??\s*$)", prompt, re.IGNORECASE | re.DOTALL)
        router_match = re.search(r'USER MESSAGE:\s*"(.*)"', prompt, re.IGNORECASE | re.DOTALL)

        if fact_match and "Answer:" in prompt and "USER MESSAGE:" not in prompt:
            # FactClassifier call path
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

        utterance = (router_match.group(1) if router_match else prompt).strip().lower()

        if any(k in utterance for k in ("open ", "close ", "screenshot", "window", "file manager")):
            return "system"
        if any(k in utterance for k in ("play", "music", "song", "track", "pause", "youtube", "skip")):
            return "media_play"
        if any(k in utterance for k in ("who are you", "what is your name", "what can you do")):
            return "identity"
        if any(
            k in utterance
            for k in (
                "who is",
                "what is",
                "latest",
                "news",
                "founded",
                "gdp",
                "runs",
                "ceo of",
                "prime minister",
                "pm of",
            )
        ):
            return "research"
        return "chat"


@pytest.fixture
def router() -> AgentRouter:
    return AgentRouter(_GoldenRouterLLM())


@pytest.fixture
def orchestrator() -> AgentOrchestrator:
    return AgentOrchestrator(MagicMock(), MagicMock())


@pytest.mark.asyncio
async def test_routing_golden_dataset(router: AgentRouter, orchestrator: AgentOrchestrator):
    time_queries = {
        "what is the time",
        "what time is it",
        "can you tell me the time",
        "current time",
    }
    for query, expected, forbidden in ROUTING_GOLDEN:
        if query in time_queries:
            intent = orchestrator._detect_direct_tool_intent(query, origin="voice")
            assert intent is not None, f"Expected get_time intent for query '{query}'"
            assert intent.tool == "get_time", f"Expected get_time for query '{query}', got '{intent.tool}'"
            continue

        route = await router.route(query, "golden_user")
        assert route == expected, f"Query '{query}' -> {route}, expected {expected}"
        if forbidden is not None:
            assert route != forbidden, f"Query '{query}' unexpectedly routed to forbidden '{forbidden}'"


def test_bootstrap_contamination_never_hits_get_time(orchestrator: AgentOrchestrator):
    for query in BOOTSTRAP_CONTAMINATION_CASES:
        augmented = BOOTSTRAP_WITH_TIME.format(query=query)
        extracted = orchestrator._extract_user_message_segment(augmented)
        assert extracted == query
        intent = orchestrator._detect_direct_tool_intent(extracted, origin="voice")
        assert intent is None or intent.tool != "get_time", (
            f"Factual query '{query}' incorrectly triggered get_time after bootstrap extraction"
        )


def test_genuine_time_queries_still_fast_path(orchestrator: AgentOrchestrator):
    for query in (
        "what is the time",
        "what time is it",
        "can you tell me the time",
        "current time",
    ):
        augmented = BOOTSTRAP_WITH_TIME.format(query=query)
        extracted = orchestrator._extract_user_message_segment(augmented)
        assert extracted == query
        intent = orchestrator._detect_direct_tool_intent(extracted, origin="voice")
        assert intent is not None, f"Expected get_time intent for query '{query}'"
        assert intent.tool == "get_time", f"Expected get_time for query '{query}', got '{intent.tool}'"
