from __future__ import annotations

import logging
import time
from typing import Any

from .research_models import ResearchResult
from .research_planner import ResearchPlanner
from .result_synthesizer import ResultSynthesizer
from .search_executor import SearchExecutor

logger = logging.getLogger(__name__)


class ResearchAgent:
    def __init__(self, role_llm: Any = None) -> None:
        self.role_llm = role_llm
        self.planner = ResearchPlanner(role_llm=role_llm)
        self.executor = SearchExecutor()
        self.synthesizer = ResultSynthesizer(role_llm=role_llm)

    async def run(
        self,
        *,
        query: str,
        user_id: str,
        session_id: str,
        trace_id: str,
    ) -> ResearchResult:
        logger.warning(
            "research_agent_deprecated_path_used query=%s user_id=%s session_id=%s trace_id=%s",
            query,
            user_id,
            session_id,
            trace_id,
        )
        started = time.monotonic()
        plan = await self.planner.plan(query)
        sources = await self.executor.execute(plan.tasks, plan.fallback_query or query)
        display_summary, voice_summary = await self.synthesizer.synthesize(query, sources)
        duration_ms = int(max(0.0, (time.monotonic() - started) * 1000.0))

        logger.info(
            "research_completed query=%s user_id=%s session_id=%s source_count=%s duration_ms=%s trace_id=%s",
            query,
            user_id,
            session_id,
            len(sources),
            duration_ms,
            trace_id,
        )

        return ResearchResult(
            summary=display_summary,
            voice_summary=voice_summary,
            sources=sources,
            query=query,
            trace_id=trace_id,
            duration_ms=duration_ms,
        )
