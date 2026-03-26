from __future__ import annotations

import json
import logging
from typing import Any

from livekit.agents.llm import ChatContext, ChatMessage

from core.llm.llm_roles import LLMRole

from .research_models import ProviderTask, ResearchPlan
from .research_task_builder import ALWAYS_SEARCH_PATTERNS, build_research_tasks

logger = logging.getLogger(__name__)


class ResearchPlanner:
    ALWAYS_SEARCH_PATTERNS = ALWAYS_SEARCH_PATTERNS

    def __init__(self, role_llm: Any = None) -> None:
        self.role_llm = role_llm

    async def plan(self, query: str) -> ResearchPlan:
        q = str(query or "").strip()
        if not q:
            return ResearchPlan(tasks=[], fallback_query="")

        deterministic, fallback_query = build_research_tasks(q)
        if deterministic:
            return ResearchPlan(tasks=deterministic, fallback_query=fallback_query)

        llm_tasks = await self._llm_plan_tasks(q)
        if llm_tasks:
            return ResearchPlan(tasks=llm_tasks[:4], fallback_query=q)

        return ResearchPlan(tasks=deterministic, fallback_query=fallback_query)

    async def _llm_plan_tasks(self, query: str) -> list[ProviderTask]:
        if self.role_llm is None:
            return []

        prompt = (
            "Break this user research question into 2-4 focused web subqueries. "
            "Return ONLY JSON: {\"subqueries\": [\"...\"]}.\n"
            f"Question: {query}"
        )
        chat_ctx = ChatContext([ChatMessage(role="user", content=[prompt])])

        try:
            stream = await self.role_llm.chat(
                role=LLMRole.PLANNER,
                chat_ctx=chat_ctx,
                tools=[],
                tool_choice="none",
            )
            content = await self._stream_to_text(stream)
            parsed = json.loads(self._extract_json_blob(content))
        except Exception as e:
            logger.info("research_planner_llm_fallback reason=%s", e)
            return []

        raw_subqueries = parsed.get("subqueries") if isinstance(parsed, dict) else None
        if not isinstance(raw_subqueries, list):
            return []

        tasks: list[ProviderTask] = []
        for subquery in raw_subqueries:
            text = str(subquery or "").strip()
            if not text:
                continue
            tasks.append(ProviderTask(provider="tavily", query=text, max_results=3))
        return tasks

    @staticmethod
    async def _stream_to_text(stream: Any) -> str:
        chunks: list[str] = []
        try:
            async for chunk in stream:
                if hasattr(chunk, "choices") and getattr(chunk, "choices", None):
                    delta = getattr(chunk.choices[0], "delta", None)
                    text = getattr(delta, "content", "") if delta is not None else ""
                elif hasattr(chunk, "delta") and getattr(chunk, "delta", None):
                    delta = chunk.delta
                    text = getattr(delta, "content", "")
                else:
                    text = str(getattr(chunk, "content", "") or "")
                if text:
                    chunks.append(text)
        finally:
            close_fn = getattr(stream, "aclose", None)
            if callable(close_fn):
                try:
                    await close_fn()
                except Exception:
                    pass
        return "".join(chunks).strip()

    @staticmethod
    def _extract_json_blob(text: str) -> str:
        stripped = str(text or "").strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end < start:
            return "{}"
        return stripped[start : end + 1]
