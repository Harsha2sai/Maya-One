from __future__ import annotations

import os

import aiohttp

from core.research.base_provider import BaseSearchProvider
from core.research.research_models import SourceItem


class SerperProvider(BaseSearchProvider):
    name = "serper"
    api_key_env = "SERPER_API_KEY"

    async def _search_impl(
        self,
        *,
        query: str,
        max_results: int,
        timeout_s: float,
    ) -> list[SourceItem]:
        api_key = os.getenv(self.api_key_env, "").strip()
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": max(1, min(max_results, 10))},
            ) as response:
                if response.status >= 400:
                    text = await response.text()
                    raise RuntimeError(f"http_{response.status}:{text[:180]}")
                data = await response.json(content_type=None)

        results: list[SourceItem] = []
        for item in (data.get("organic") or [])[:max_results]:
            link = str(item.get("link") or "").strip()
            if not link:
                continue
            results.append(
                self._item(
                    title=str(item.get("title") or "Serper result"),
                    url=link,
                    snippet=str(item.get("snippet") or ""),
                )
            )
        return results
