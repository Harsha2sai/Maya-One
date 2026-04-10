import pytest

from core.action.constants import RoutePrecedence
from core.action.precedence import RouteCandidate, RoutePrecedenceResolver
from core.orchestrator.agent_router import AgentRouter


def test_route_precedence_resolver_prefers_highest_priority() -> None:
    resolver = RoutePrecedenceResolver()
    resolved = resolver.resolve(
        [
            RouteCandidate(route="chat", precedence=RoutePrecedence.CONVERSATIONAL_FALLBACK),
            RouteCandidate(route="system", precedence=RoutePrecedence.SYSTEM_PLANNER_EXPLICIT),
        ]
    )
    assert resolved.route == "system"
    assert resolved.ask_clarification is False


def test_route_precedence_resolver_conflict_requires_clarification() -> None:
    resolver = RoutePrecedenceResolver()
    resolved = resolver.resolve(
        [
            RouteCandidate(route="media_play", precedence=RoutePrecedence.LLM_TOOL_DETERMINISTIC, target="media"),
            RouteCandidate(route="scheduling", precedence=RoutePrecedence.LLM_TOOL_DETERMINISTIC, target="schedule"),
        ]
    )
    assert resolved.route == "chat"
    assert resolved.ask_clarification is True


@pytest.mark.asyncio
async def test_agent_router_sets_pending_clarification_on_same_rank_conflict() -> None:
    class _DummyLLM:
        async def chat(self, *args, **kwargs):
            del args, kwargs
            return "chat"

    router = AgentRouter(_DummyLLM())
    route = await router.route("play music and set a reminder", user_id="u1")
    clarification = router.consume_pending_clarification("u1")
    assert route == "chat"
    assert "multiple possible actions" in clarification.lower()

