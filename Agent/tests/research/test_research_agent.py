from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.research.research_agent import ResearchAgent
from core.research.research_models import ProviderTask, ResearchPlan, SourceItem


@pytest.mark.asyncio
async def test_research_agent_runs_pipeline() -> None:
    agent = ResearchAgent(role_llm=None)
    agent.planner.plan = AsyncMock(
        return_value=ResearchPlan(tasks=[ProviderTask(provider="tavily", query="q")], fallback_query="q")
    )
    sources = [
        SourceItem.from_values(
            title="T1",
            url="https://example.com/t1",
            snippet="snippet",
            provider="tavily",
        )
    ]
    agent.executor.execute = AsyncMock(return_value=sources)
    agent.synthesizer.synthesize = AsyncMock(return_value=("summary text", "voice text"))

    result = await agent.run(
        query="latest ai news",
        user_id="u1",
        session_id="s1",
        trace_id="trace-1",
    )

    assert result.summary == "summary text"
    assert result.voice_summary == "voice text"
    assert len(result.sources) == 1
    assert result.trace_id == "trace-1"
    assert result.duration_ms >= 0
