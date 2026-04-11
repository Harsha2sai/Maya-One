"""Built-in skill wrapper for web search workflow."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional

from core.tools import web as web_tools

from ..base import BaseSkill, SkillPermissionLevel, SkillResult


class WebSearchSkill(BaseSkill):
    def __init__(self, *, search_fn: Optional[Callable[..., Any]] = None) -> None:
        super().__init__(
            name="web_search",
            description="Search the web and return structured results",
            permission_level=SkillPermissionLevel.NETWORK,
            permission_tool_name="web_search",
        )
        self._search_fn = search_fn or web_tools.web_search

    def validate(self, params: Dict[str, Any]) -> bool:
        if not super().validate(params):
            return False
        return bool(str((params or {}).get("query") or "").strip())

    async def execute(self, params: Dict[str, Any]) -> SkillResult:
        query = str((params or {}).get("query") or "").strip()
        max_results = int((params or {}).get("max_results") or 10)

        maybe = self._search_fn(query=query, max_results=max_results)
        result = await maybe if asyncio.iscoroutine(maybe) else maybe

        if hasattr(result, "model_dump") and callable(result.model_dump):
            payload = result.model_dump()
        elif isinstance(result, dict):
            payload = dict(result)
        else:
            payload = {"result": result}

        success = bool(payload.get("success", True))
        return SkillResult(success=success, data=payload, error=payload.get("error"))
