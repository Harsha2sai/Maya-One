from __future__ import annotations

import os

from core.research.base_provider import BaseSearchProvider
from core.research.research_models import SourceItem


class TavilyProvider(BaseSearchProvider):
    name = "tavily"
    api_key_env = "TAVILY_API_KEY"

    async def _search_impl(
        self,
        *,
        query: str,
        max_results: int,
        timeout_s: float,
    ) -> list[SourceItem]:
        api_key = os.getenv(self.api_key_env, "").strip()
        payload = {
            "api_key": api_key,
            "query": query,
            "max_results": max(1, min(max_results, 8)),
            "search_depth": "advanced",
            "include_answer": False,
            "include_raw_content": False,
        }
        # Use POST without adding another helper; keep API call local.
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://api.tavily.com/search",
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status >= 400:
                    text = await response.text()
                    raise RuntimeError(f"http_{response.status}:{text[:180]}")
                data = await response.json(content_type=None)

        results: list[SourceItem] = []
        for item in (data.get("results") or [])[:max_results]:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            results.append(
                self._item(
                    title=str(item.get("title") or "Tavily result"),
                    url=url,
                    snippet=str(item.get("content") or item.get("snippet") or ""),
                )
            )
        return results
