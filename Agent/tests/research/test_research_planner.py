from __future__ import annotations

import pytest

from core.research.research_models import ProviderTask
from core.research.research_planner import ResearchPlanner


@pytest.mark.asyncio
async def test_weather_query_routes_to_weather_provider() -> None:
    planner = ResearchPlanner(role_llm=None)
    plan = await planner.plan("what is the weather in hyderabad")

    providers = [task.provider for task in plan.tasks]
    assert "weather" in providers
    assert plan.fallback_query == "what is the weather in hyderabad"


@pytest.mark.asyncio
async def test_finance_query_routes_to_finance_and_news() -> None:
    planner = ResearchPlanner(role_llm=None)
    plan = await planner.plan("tesla stock price and latest news")

    providers = [task.provider for task in plan.tasks]
    assert "finance" in providers
    assert "news" in providers


@pytest.mark.asyncio
async def test_generic_query_uses_fallback_plan() -> None:
    planner = ResearchPlanner(role_llm=None)
    plan = await planner.plan("explain zero shot learning")

    assert len(plan.tasks) >= 1
    assert isinstance(plan.tasks[0], ProviderTask)


@pytest.mark.asyncio
async def test_empty_query_returns_empty_plan() -> None:
    planner = ResearchPlanner(role_llm=None)
    plan = await planner.plan("   ")

    assert plan.tasks == []
    assert plan.fallback_query == ""


class _BadRoleLLM:
    async def chat(self, **_kwargs):
        raise RuntimeError("planner unavailable")


@pytest.mark.asyncio
async def test_llm_planner_failure_falls_back_to_default_plan() -> None:
    planner = ResearchPlanner(role_llm=_BadRoleLLM())
    plan = await planner.plan("latest ai policy updates")

    assert len(plan.tasks) >= 1


@pytest.mark.asyncio
async def test_role_status_queries_force_always_search_tasks() -> None:
    planner = ResearchPlanner(role_llm=None)
    plan = await planner.plan("who is the ceo of openai")

    providers = [task.provider for task in plan.tasks]
    assert "news" in providers
    assert "tavily" in providers
